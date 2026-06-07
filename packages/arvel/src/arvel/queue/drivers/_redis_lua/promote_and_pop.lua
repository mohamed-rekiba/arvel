-- Atomic promote-and-pop for the arvel redis-direct queue driver.
--
-- KEYS[1] = <queue_key>:<queue>:scheduled  (ZSET; score = available_at_ms; member = envelope JSON)
-- KEYS[2] = <queue_key>:<queue>:ready      (ZSET; score = -priority*SCALE + enqueue_ms; member = envelope JSON)
-- ARGV[1] = now_ms (integer)
--
-- Step 1: move every member of `scheduled` with score <= now_ms into `ready`.
--         New score = -priority*SCALE + available_at_ms, so ready entries sort
--         by priority first and by time (FIFO) within a priority. SCALE mirrors
--         _PRIORITY_SCALE in redis.py — keep both in sync.
-- Step 2: ZPOPMIN `ready` (highest priority — lowest score — wins).
-- Returns nil if no envelope is ready; otherwise the envelope JSON.

local scheduled = KEYS[1]
local ready = KEYS[2]
local now_ms = tonumber(ARGV[1])
local SCALE = 10000000000000  -- 1e13

-- Step 1: promote due-now scheduled entries (WITHSCORES gives available_at_ms)
local due = redis.call('ZRANGEBYSCORE', scheduled, '-inf', now_ms, 'WITHSCORES')
if #due > 0 then
    local promoted = {}
    for i = 1, #due, 2 do
        local member = due[i]
        local available_at_ms = tonumber(due[i + 1])
        -- Extract priority from the JSON envelope. Members are framework-produced
        -- so a simple substring match is sufficient and avoids a Lua JSON parser.
        local p = string.match(member, '"priority"%s*:%s*(%-?%d+)')
        local priority = tonumber(p) or 0
        local score = -priority * SCALE + available_at_ms
        -- Format as a plain integer string — passing a Lua double straight to
        -- ZADD risks scientific notation and lost precision.
        redis.call('ZADD', ready, string.format('%.0f', score), member)
        promoted[#promoted + 1] = member
    end
    redis.call('ZREM', scheduled, unpack(promoted))
end

-- Step 2: pop highest priority (lowest score)
local popped = redis.call('ZPOPMIN', ready, 1)
if #popped == 0 then
    return nil
end
return popped[1]
