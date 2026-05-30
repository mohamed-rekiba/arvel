-- Atomic promote-and-pop for the arvel redis-direct queue driver (WI-018, ADR-066).
--
-- KEYS[1] = <queue_key>:<queue>:scheduled  (ZSET; score = available_at_ms; member = envelope JSON)
-- KEYS[2] = <queue_key>:<queue>:ready      (ZSET; score = -priority; member = envelope JSON)
-- ARGV[1] = now_ms (integer)
--
-- Step 1: move every member of `scheduled` with score <= now_ms into `ready`.
--         New score = -<priority parsed out of the envelope JSON>.
-- Step 2: ZPOPMIN `ready` (highest priority — lowest score — wins).
-- Returns nil if no envelope is ready; otherwise the envelope JSON.

local scheduled = KEYS[1]
local ready = KEYS[2]
local now_ms = tonumber(ARGV[1])

-- Step 1: promote due-now scheduled entries
local due = redis.call('ZRANGEBYSCORE', scheduled, '-inf', now_ms)
if #due > 0 then
    for i = 1, #due do
        local member = due[i]
        -- Extract priority from the JSON envelope. Members are framework-produced
        -- so a simple substring match is sufficient and avoids a Lua JSON parser.
        local p = string.match(member, '"priority"%s*:%s*(%-?%d+)')
        local priority = tonumber(p) or 0
        redis.call('ZADD', ready, -priority, member)
    end
    redis.call('ZREM', scheduled, unpack(due))
end

-- Step 2: pop highest priority (lowest score)
local popped = redis.call('ZPOPMIN', ready, 1)
if #popped == 0 then
    return nil
end
return popped[1]
