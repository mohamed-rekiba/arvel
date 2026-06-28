/* arvel home — "snake game" background.
   One or two snakes wander the dot lattice (random turns, bouncing off edges),
   lighting up dots in the brand color with a fading tail. Subtle, behind the
   hero content. Honors prefers-reduced-motion (no animation at all). */
(function () {
  function init() {
    var c = document.querySelector('.ah-snake');
    if (!c || c.__snake) return;
    if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    c.__snake = true;

    var ctx = c.getContext('2d');
    var DPR = Math.min(window.devicePixelRatio || 1, 2);
    var GRID = 22, cols = 2, rows = 2, W = 0, H = 0;

    function size() {
      var p = c.parentElement; if (!p) return;
      var r = p.getBoundingClientRect();
      W = r.width; H = r.height;
      c.width = Math.max(1, Math.round(W * DPR));
      c.height = Math.max(1, Math.round(H * DPR));
      ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
      cols = Math.max(2, Math.floor(W / GRID));
      rows = Math.max(2, Math.floor(H / GRID));
    }
    size();
    window.addEventListener('resize', size);

    var dirs = [[1, 0], [-1, 0], [0, 1], [0, -1]];
    function rnd(n) { return Math.floor(Math.random() * n); }
    function makeSnake() {
      // always spawn at a random cell inside the hero
      return { x: rnd(cols), y: rnd(rows), dir: dirs[rnd(4)], body: [], len: 13 + rnd(9) };
    }
    var COUNT = 3;
    var snakes = [];
    for (var k = 0; k < COUNT; k++) snakes.push(makeSnake());

    function step(s) {
      if (Math.random() < 0.22) { // random play: occasionally turn (never reverse)
        var opts = dirs.filter(function (d) { return !(d[0] === -s.dir[0] && d[1] === -s.dir[1]); });
        s.dir = opts[rnd(opts.length)];
      }
      s.x += s.dir[0]; s.y += s.dir[1];
      if (s.x < 0) { s.x = 0; s.dir = [1, 0]; } else if (s.x >= cols) { s.x = cols - 1; s.dir = [-1, 0]; }
      if (s.y < 0) { s.y = 0; s.dir = [0, 1]; } else if (s.y >= rows) { s.y = rows - 1; s.dir = [0, -1]; }
      s.body.push([s.x, s.y]);
      while (s.body.length > s.len) s.body.shift();
    }

    function color() {
      var sc = document.body.getAttribute('data-md-color-scheme');
      return sc === 'slate' ? [123, 189, 232] : [10, 65, 116];
    }

    var acc = 0, STEP = 135, last = performance.now();
    function frame(now) {
      if (!c.isConnected) { c.__snake = false; return; } // stop if removed (instant nav)
      var dt = Math.min(now - last, 250); last = now; acc += dt;
      while (acc >= STEP) { snakes.forEach(step); acc -= STEP; }

      ctx.clearRect(0, 0, W, H);
      var rgb = color(), pre = 'rgba(' + rgb[0] + ',' + rgb[1] + ',' + rgb[2] + ',';
      snakes.forEach(function (s) {
        for (var i = 0; i < s.body.length; i++) {
          var p = s.body[i], t = (i + 1) / s.body.length;     // tail 0 → head 1
          var a = Math.pow(t, 1.5) * 0.85;                     // head brightest
          var rad = 1.6 + t * 2.1;
          ctx.beginPath();
          ctx.fillStyle = pre + a.toFixed(3) + ')';
          ctx.arc(p[0] * GRID + GRID / 2, p[1] * GRID + GRID / 2, rad, 0, 6.2832);
          ctx.fill();
        }
        var h = s.body[s.body.length - 1];                     // soft glow at the head
        if (h) {
          ctx.beginPath();
          ctx.fillStyle = pre + '0.22)';
          ctx.arc(h[0] * GRID + GRID / 2, h[1] * GRID + GRID / 2, 7, 0, 6.2832);
          ctx.fill();
        }
      });
      requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
  }

  // Run on load, and re-init on Material's instant navigation if present.
  if (window.document$ && typeof window.document$.subscribe === 'function') {
    window.document$.subscribe(function () { init(); });
  } else if (document.readyState !== 'loading') {
    init();
  } else {
    document.addEventListener('DOMContentLoaded', init);
  }
})();
