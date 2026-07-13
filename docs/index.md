---
title: arvel — a batteries-included async web framework for Python
hide:
  - navigation
  - toc
---

<div class="arvel-home">

<!-- ===================== HERO ===================== -->
<section class="ah-hero">
  <canvas class="ah-snake" aria-hidden="true"></canvas>
  <div class="ah-hero__inner ah-wrap">
    <div class="ah-hero__copy">
      <h1 class="ah-h1">The async web framework <span class="hl">for Python.</span></h1>
      <p class="ah-lead">Batteries-included and type-safe — routing, ORM, queue, cache, auth, mail, views, and a fast CLI in one coherent toolkit.</p>
      <div class="ah-cta">
        <a class="ah-btn ah-btn--primary" href="getting-started/">Get started →</a>
        <a class="ah-btn ah-btn--ghost" href="database/">Read the docs</a>
      </div>
      <div class="ah-install"><span><span class="p">$</span> uv tool install arvel</span><button type="button" class="cp" onclick="navigator.clipboard&amp;&amp;navigator.clipboard.writeText('uv tool install arvel');this.textContent='Copied ✓';setTimeout(()=>{this.textContent='Copy ⧉'},1500)">⧉</button></div>
      <div class="ah-micro"><span>◇ MIT licensed</span><span>⚡ Python 3.14+</span><span>◧ Zero heavy deps at import</span></div>
    </div>
    <div class="ah-hero__win">
      <div class="ah-win">
        <div class="ah-win__bar"><span class="ah-dots"><i style="background:#FF5F57"></i><i style="background:#FEBC2E"></i><i style="background:#28C840"></i></span><span class="ah-fname">app/routes.py</span></div>
<pre class="ah-code"><span class="tk">from</span> <span class="tn">arvel</span> <span class="tk">import</span> <span class="tn">Route</span><span class="tde">,</span> <span class="tn">Model</span>

<span class="tk">class</span> <span class="tfn">Post</span><span class="tde">(</span><span class="tn">Model</span><span class="tde">):</span>
    <span class="tn">__fillable__</span> <span class="tde">=</span> <span class="tde">[</span><span class="ts">"title"</span><span class="tde">,</span> <span class="ts">"body"</span><span class="tde">]</span>

<span class="tc"># eager-load the author relation — no N+1</span>
<span class="tn">posts</span> <span class="tde">=</span> <span class="tk">await</span> <span class="tn">Post</span><span class="tde">.</span><span class="tfn">with_</span><span class="tde">(</span><span class="ts">"author"</span><span class="tde">)</span> \
    <span class="tde">.</span><span class="tfn">where</span><span class="tde">(</span><span class="tn">published</span><span class="tde">=</span><span class="tk">True</span><span class="tde">).</span><span class="tfn">get</span><span class="tde">()</span>

<span class="tn">Route</span><span class="tde">.</span><span class="tfn">resource</span><span class="tde">(</span><span class="ts">"posts"</span><span class="tde">,</span> <span class="tn">PostController</span><span class="tde">)</span>  <span class="tc"># 7 routes</span></pre>
      </div>
    </div>
  </div>
</section>

<!-- ===================== FEATURES ===================== -->
<section class="ah-block">
  <div class="ah-wrap">
    <div class="ah-eyebrow">Why arvel</div>
    <h2 class="ah-h2">Everything you need, natively async.</h2>
    <p class="ah-sub">Every layer is async to the core and strictly typed — so concurrency is the default and your editor catches mistakes before CI does.</p>
    <div class="ah-feats">
      <div class="ah-feat"><div class="ah-feat__ic">⚡</div><h3>Async-first</h3><p>Routing, ORM, queues, mail and cache are async end-to-end. High-concurrency Python without blocking surprises.</p><span class="ah-tag">async / await</span></div>
      <div class="ah-feat"><div class="ah-feat__ic">◇</div><h3>Type-safe to the core</h3><p>Strict static typing on every public API, modern generics, and mechanically-enforced boundaries.</p><span class="ah-tag">strict typing</span></div>
      <div class="ah-feat"><div class="ah-feat__ic">⊞</div><h3>Batteries included</h3><p>ORM, Auth, validation, queues, events, mail, notifications, storage, templates and a test kit — one toolkit.</p><span class="ah-tag">one toolkit</span></div>
      <div class="ah-feat"><div class="ah-feat__ic">▤</div><h3>An ORM you'll enjoy</h3><p>Active-Record with relations, eager loading, soft-deletes, casts and migrations — no N+1, multi-dialect SQL.</p><span class="ah-tag">no N+1</span></div>
      <div class="ah-feat"><div class="ah-feat__ic">◈</div><h3>A first-class CLI</h3><p>Scaffold apps, run migrations, drive queue workers and open a REPL — all from one fast command.</p><span class="ah-tag">arvel new</span></div>
      <div class="ah-feat"><div class="ah-feat__ic">◧</div><h3>Light by default</h3><p><code>import arvel</code> pulls zero heavy libraries. Each capability loads only when you use it.</p><span class="ah-tag">lazy imports</span></div>
    </div>
  </div>
</section>

<!-- ===================== SHOWCASE ===================== -->
<div class="ah-showcase">
  <div class="ah-wrap ah-block">
    <div class="ah-eyebrow">A taste</div>
    <h2 class="ah-h2">Familiar, expressive, type-safe.</h2>
    <p class="ah-sub">Resource routes, relations, dispatchable jobs and fluent validation — clean, readable APIs with Python types from end to end.</p>
    <div class="ah-win ah-win--wide">
      <div class="ah-win__bar"><span class="ah-dots"><i style="background:#FF5F57"></i><i style="background:#FEBC2E"></i><i style="background:#28C840"></i></span><span class="ah-fname">app/routes.py</span></div>
<pre class="ah-code"><span class="tk">from</span> <span class="tn">arvel</span> <span class="tk">import</span> <span class="tn">Route</span>

<span class="tn">Route</span><span class="tde">.</span><span class="tfn">resource</span><span class="tde">(</span><span class="ts">"posts"</span><span class="tde">,</span> <span class="tn">PostController</span><span class="tde">)</span>        <span class="tc"># 7 RESTful routes</span>
<span class="tn">Route</span><span class="tde">.</span><span class="tfn">get</span><span class="tde">(</span><span class="ts">"/users/{user}"</span><span class="tde">,</span> <span class="tn">show</span><span class="tde">,</span> <span class="tn">name</span><span class="tde">=</span><span class="ts">"users.show"</span><span class="tde">)</span>

<span class="tn">Route</span><span class="tde">.</span><span class="tfn">middleware</span><span class="tde">(</span><span class="ts">"auth"</span><span class="tde">).</span><span class="tfn">group</span><span class="tde">(</span><span class="tk">lambda</span><span class="tde">:</span> <span class="tde">(</span>
    <span class="tn">Route</span><span class="tde">.</span><span class="tfn">post</span><span class="tde">(</span><span class="ts">"/posts"</span><span class="tde">,</span> <span class="tn">store</span><span class="tde">),</span>
<span class="tde">))</span></pre>
    </div>
  </div>
</div>

<!-- ===================== FOUR GATES ===================== -->
<section class="ah-block">
  <div class="ah-wrap">
    <div class="ah-eyebrow">Enforced from the first commit</div>
    <h2 class="ah-h2">Four gates keep the framework honest.</h2>
    <p class="ah-sub">Not aspirations — CI checks. Every commit must pass all four, so quality is mechanical, not a matter of discipline.</p>
    <div class="ah-gates">
      <div class="ah-gate"><span class="ah-gate__g">G1</span><h4>Boundaries</h4><p>import-linter keeps modules honest: kernel isolation, a layered DAG, no heavy import at load.</p></div>
      <div class="ah-gate"><span class="ah-gate__g">G2</span><h4>Startup</h4><p><code>import arvel</code> pulls zero heavy libraries; the CLI stays instant.</p></div>
      <div class="ah-gate"><span class="ah-gate__g">G3</span><h4>Types</h4><p>Strict mypy + pyright on every public API surface.</p></div>
      <div class="ah-gate"><span class="ah-gate__g">G4</span><h4>Verified behavior</h4><p>Every capability is exercised by a dedicated per-module test, proving it works as documented.</p></div>
    </div>
  </div>
</section>

<!-- ===================== CTA BAND ===================== -->
<div class="ah-cta-band">
  <div class="ah-wrap ah-cta-band__inner">
    <img src="assets/arvel-mark-dark.svg" alt="" class="ah-cta-band__mark">
    <h2>Ready to build?</h2>
    <p>Scaffold an app and serve it in under a minute.</p>
    <div class="ah-cta" style="justify-content:center">
      <a class="ah-btn ah-btn--primary" href="getting-started/">Get started →</a>
      <a class="ah-btn ah-btn--onnavy" href="architecture/">Browse the architecture</a>
    </div>
  </div>
</div>

</div>
