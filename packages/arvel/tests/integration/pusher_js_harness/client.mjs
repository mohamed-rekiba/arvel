// Pusher v7 wire-contract harness — drives pusher-js@8.5.0 against a
// Python-managed ReverbServer and emits every received frame to stdout
// as one JSON line per frame.
//
// stdout protocol (one line per frame):
//   {"event": "<event-name>", "channel": "<channel-name-or-null>", "data": <string-or-object>}
//
// Invocation: node client.mjs --url ws://host:port --key APP_KEY --channel CHANNEL
//
// Exits non-zero on argv error. Otherwise runs until SIGTERM (the Python
// driver kills the subprocess after assertions complete).

import { Pusher } from 'pusher-js';

function parseArgs(argv) {
  const out = { url: null, key: null, channel: null };
  for (let i = 2; i < argv.length; i++) {
    const flag = argv[i];
    const value = argv[i + 1];
    if (flag === '--url') { out.url = value; i++; }
    else if (flag === '--key') { out.key = value; i++; }
    else if (flag === '--channel') { out.channel = value; i++; }
  }
  if (!out.url || !out.key || !out.channel) {
    process.stderr.write('usage: client.mjs --url WS_URL --key APP_KEY --channel CHANNEL\n');
    process.exit(2);
  }
  return out;
}

function emit(event, channel, data) {
  process.stdout.write(JSON.stringify({ event, channel, data }) + '\n');
}

const args = parseArgs(process.argv);

const parsed = new URL(args.url);
const wsHost = parsed.hostname;
const wsPort = parseInt(parsed.port, 10) || 6001;
const forceTLS = parsed.protocol === 'wss:';

// Pusher.logToConsole would dump to stderr; we want clean stdout for the protocol stream only.
const pusher = new Pusher(args.key, {
  wsHost,
  wsPort,
  wssPort: wsPort,
  forceTLS,
  enabledTransports: ['ws', 'wss'],
  cluster: 'mt1',
});

// pusher-js exposes all_events at the connection layer; we hook the channel and the connection.
pusher.connection.bind('connected', () => {
  emit('pusher:connection_established', null, JSON.stringify({
    socket_id: pusher.connection.socket_id,
  }));
});

pusher.connection.bind('error', (err) => {
  emit('pusher:error', null, JSON.stringify({
    message: String(err && err.error && err.error.data && err.error.data.message || err),
  }));
});

pusher.connection.bind('disconnected', () => {
  emit('pusher:disconnected', null, '');
});

const channel = pusher.subscribe(args.channel);

channel.bind('pusher:subscription_succeeded', () => {
  emit('pusher_internal:subscription_succeeded', args.channel, '{}');
});
channel.bind('pusher:subscription_error', (data) => {
  emit('pusher_internal:subscription_error', args.channel, JSON.stringify(data || {}));
});
channel.bind_global((event, data) => {
  // Skip the synthetic pusher:* ones already emitted above.
  if (event === 'pusher:subscription_succeeded' || event === 'pusher:subscription_error') return;
  emit(event, args.channel, typeof data === 'string' ? data : JSON.stringify(data));
});

process.on('SIGTERM', () => {
  pusher.disconnect();
  process.exit(0);
});
process.on('SIGINT', () => {
  pusher.disconnect();
  process.exit(0);
});
