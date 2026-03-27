export default function OptionRidersLandingPage() {
  const features = [
    {
      icon: "⚡",
      title: "Ranked Intraday Watchlist",
      text: "Strongest options names first — direction, entry, target, stop, and catalyst in one clean view.",
      accent: "cyan",
    },
    {
      icon: "🔥",
      title: "Unusual + Most Traded Options",
      text: "Spot where size, liquidity, and urgency are building before the crowd catches on.",
      accent: "amber",
    },
    {
      icon: "🎯",
      title: "ATM Spread Check",
      text: "Know if a name is actually tradable before you commit capital. No more garbage fills.",
      accent: "emerald",
    },
    {
      icon: "📊",
      title: "Session Context Built In",
      text: "Market overview, economic events, themes, and ticker detail — trade the day with structure.",
      accent: "purple",
    },
  ];

  const dashboardRows = [
    { ticker: "SPY", dir: "Short", entry: "Below 661", target: "656–652", stop: "668", pct: "-0.42%" },
    { ticker: "QQQ", dir: "Short", entry: "Below 591", target: "585–580", stop: "600", pct: "-0.58%" },
    { ticker: "NVDA", dir: "Long", entry: "Above 184", target: "190–195", stop: "178", pct: "+1.24%" },
    { ticker: "MU", dir: "Long", entry: "Above 430", target: "445–450", stop: "418", pct: "+0.89%" },
  ];

  const faqs = [
    {
      q: "What do I get with Option Riders?",
      a: "Live dashboard with ranked watchlists, options flow, spread checks, and session context — plus access to the private TradingView script if you choose.",
    },
    {
      q: "Who is this for?",
      a: "Built for intraday traders who want cleaner selection, better process, and a faster way to focus on liquid options setups.",
    },
    {
      q: "Why does the spread check matter?",
      a: "A setup can look great on the chart and still be a terrible trade if the options chain is too wide. This keeps you out of junk.",
    },
    {
      q: "Is this for long-term investors?",
      a: "No. Designed exclusively for active traders focused on the current session and execution quality.",
    },
  ];

  const accentClasses = {
    cyan: { border: "border-cyan-400/20", bg: "bg-cyan-400/[0.06]", icon: "bg-cyan-400/15 text-cyan-300", dot: "bg-cyan-400" },
    amber: { border: "border-amber-400/20", bg: "bg-amber-400/[0.05]", icon: "bg-amber-400/15 text-amber-300", dot: "bg-amber-400" },
    emerald: { border: "border-emerald-400/20", bg: "bg-emerald-400/[0.06]", icon: "bg-emerald-400/15 text-emerald-300", dot: "bg-emerald-400" },
    purple: { border: "border-purple-400/20", bg: "bg-purple-400/[0.06]", icon: "bg-purple-400/15 text-purple-300", dot: "bg-purple-400" },
  };

  return (
    <div className="min-h-screen bg-[#060810] text-white font-sans antialiased" style={{ fontFamily: "'Inter', system-ui, sans-serif" }}>
      {/* Ambient background */}
      <div className="fixed inset-0 -z-10 overflow-hidden">
        <div className="absolute top-0 left-1/4 w-[600px] h-[600px] bg-cyan-500/[0.06] rounded-full blur-[120px]" />
        <div className="absolute top-0 right-1/4 w-[500px] h-[400px] bg-amber-500/[0.05] rounded-full blur-[100px]" />
        <div className="absolute bottom-1/3 left-1/2 -translate-x-1/2 w-[800px] h-[300px] bg-emerald-500/[0.04] rounded-full blur-[120px]" />
        <div
          className="absolute inset-0"
          style={{
            backgroundImage:
              "radial-gradient(circle at 1px 1px, rgba(255,255,255,0.015) 1px, transparent 0)",
            backgroundSize: "40px 40px",
          }}
        />
      </div>

      {/* ─── NAV ─────────────────────────────────────────────────── */}
      <nav className="sticky top-0 z-50 border-b border-white/[0.06] bg-[#060810]/80 backdrop-blur-xl">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4 md:px-10">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl border border-white/10 bg-gradient-to-br from-cyan-400/20 to-emerald-400/10">
              <span className="text-base">🐎</span>
            </div>
            <span className="text-lg font-semibold tracking-tight">OptionRiders</span>
          </div>
          <div className="hidden items-center gap-6 text-sm text-white/50 md:flex">
            <a href="#features" className="transition hover:text-white">Features</a>
            <a href="#access" className="transition hover:text-white">Access</a>
            <a href="#script" className="transition hover:text-white">Script</a>
            <a href="#faq" className="transition hover:text-white">FAQ</a>
          </div>
          <a
            href="#access"
            className="rounded-xl bg-gradient-to-r from-emerald-400 to-cyan-400 px-4 py-2 text-sm font-semibold text-black transition hover:opacity-90"
          >
            Get Access →
          </a>
        </div>
      </nav>

      {/* ─── HERO ────────────────────────────────────────────────── */}
      <section className="relative overflow-hidden">
        <div className="mx-auto max-w-7xl px-6 pb-24 pt-20 md:px-10 lg:pt-28 lg:pb-32">

          {/* Pill */}
          <div className="mb-8 flex justify-center">
            <div className="inline-flex items-center gap-2 rounded-full border border-emerald-400/20 bg-emerald-400/[0.07] px-4 py-2 text-sm text-emerald-300">
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400" />
              </span>
              Free dashboard · Paid TradingView script available
            </div>
          </div>

          {/* Headline */}
          <div className="mx-auto max-w-5xl text-center">
            <h1 className="text-5xl font-bold leading-[1.04] tracking-[-0.03em] md:text-6xl lg:text-7xl xl:text-8xl">
              <span className="block text-white">Trade smarter.</span>
              <span
                className="block"
                style={{
                  background: "linear-gradient(135deg, #34d399 0%, #22d3ee 50%, #38bdf8 100%)",
                  WebkitBackgroundClip: "text",
                  WebkitTextFillColor: "transparent",
                }}
              >
                Ride with edge.
              </span>
            </h1>
            <p className="mx-auto mt-7 max-w-2xl text-lg leading-relaxed text-white/55 md:text-xl">
              The free intraday dashboard options traders actually use — ranked watchlists, real options flow, spread checks, and session context. Add the TradingView script when you're ready for more.
            </p>
            <div className="mt-10 flex flex-col items-center justify-center gap-3 sm:flex-row">
              <a
                href="#access"
                className="group flex items-center gap-2 rounded-2xl bg-gradient-to-r from-emerald-400 via-cyan-400 to-sky-400 px-7 py-4 text-base font-semibold text-black shadow-[0_0_50px_rgba(0,224,255,0.2)] transition hover:shadow-[0_0_70px_rgba(0,224,255,0.35)] hover:scale-[1.02]"
              >
                Use The Free Dashboard
                <span className="transition group-hover:translate-x-0.5">→</span>
              </a>
              <a
                href="#script"
                className="rounded-2xl border border-white/10 bg-white/[0.04] px-7 py-4 text-base font-semibold text-white/80 transition hover:bg-white/[0.08] hover:text-white"
              >
                View TradingView Script
              </a>
            </div>
          </div>

          {/* Stats strip */}
          <div className="mx-auto mt-16 grid max-w-3xl grid-cols-2 gap-4 sm:grid-cols-4">
            {[
              { val: "Free", sub: "Dashboard" },
              { val: "Live", sub: "Options Flow" },
              { val: "Tight", sub: "Spread Checks" },
              { val: "Paid", sub: "TV Script" },
            ].map(({ val, sub }) => (
              <div key={sub} className="rounded-2xl border border-white/[0.07] bg-white/[0.03] p-5 text-center backdrop-blur">
                <div className="text-2xl font-bold tracking-tight">{val}</div>
                <div className="mt-1 text-xs uppercase tracking-widest text-white/35">{sub}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ─── LIVE DASHBOARD PREVIEW ──────────────────────────────── */}
      <section id="dashboard" className="border-y border-white/[0.06] bg-[#070a12]">
        <div className="mx-auto max-w-7xl px-6 py-20 md:px-10 lg:py-28">
          <div className="mb-12 flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
            <div>
              <p className="text-xs uppercase tracking-[0.28em] text-cyan-400/60">Live Preview</p>
              <h2 className="mt-3 text-3xl font-bold tracking-tight md:text-4xl">Today's trade dashboard</h2>
            </div>
            <div className="flex flex-wrap gap-2">
              <span className="rounded-full border border-amber-400/25 bg-amber-400/10 px-3 py-1.5 text-xs font-medium text-amber-300">FOMC Week</span>
              <span className="rounded-full border border-red-400/25 bg-red-400/10 px-3 py-1.5 text-xs font-medium text-red-300">Bearish Bias</span>
              <span className="rounded-full border border-white/10 bg-white/[0.04] px-3 py-1.5 text-xs font-medium text-white/50">NVDA GTC 11am PT</span>
            </div>
          </div>

          <div className="overflow-hidden rounded-[1.75rem] border border-white/[0.08] bg-[#0a0d18] shadow-[0_0_80px_rgba(0,0,0,0.5)]">
            {/* Table header */}
            <div className="grid grid-cols-6 border-b border-white/[0.06] bg-white/[0.03] px-6 py-3 text-[10px] uppercase tracking-[0.22em] text-white/30">
              <span>Ticker</span>
              <span>Direction</span>
              <span>Entry</span>
              <span>Target</span>
              <span>Stop</span>
              <span className="text-right">Change</span>
            </div>
            {dashboardRows.map((row, i) => (
              <div
                key={row.ticker}
                className={`grid grid-cols-6 items-center px-6 py-4 text-sm transition hover:bg-white/[0.025] ${
                  i !== dashboardRows.length - 1 ? "border-b border-white/[0.05]" : ""
                }`}
              >
                <span className="font-bold tracking-tight">{row.ticker}</span>
                <span>
                  <span
                    className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ${
                      row.dir === "Long"
                        ? "bg-emerald-400/10 text-emerald-300 border border-emerald-400/20"
                        : "bg-red-400/10 text-red-300 border border-red-400/20"
                    }`}
                  >
                    <span>{row.dir === "Long" ? "▲" : "▼"}</span>
                    {row.dir}
                  </span>
                </span>
                <span className="text-white/60">{row.entry}</span>
                <span className="text-white/60">{row.target}</span>
                <span className="text-white/60">{row.stop}</span>
                <span className={`text-right text-xs font-semibold ${row.pct.startsWith("+") ? "text-emerald-400" : "text-red-400"}`}>
                  {row.pct}
                </span>
              </div>
            ))}
            {/* Bottom panel */}
            <div className="grid gap-px bg-white/[0.04] sm:grid-cols-3">
              {[
                { label: "Unusual Options", desc: "Call/put activity + most traded contracts", color: "cyan" },
                { label: "ATM Spread Check", desc: "Know if the trade is actually tradable", color: "amber" },
                { label: "Ticker Detail", desc: "Catalyst, structure, levels, and bias", color: "emerald" },
              ].map(({ label, desc, color }) => (
                <div key={label} className="bg-[#0a0d18] p-5">
                  <div
                    className={`mb-2 text-xs font-semibold uppercase tracking-wider ${
                      color === "cyan" ? "text-cyan-400" : color === "amber" ? "text-amber-400" : "text-emerald-400"
                    }`}
                  >
                    {label}
                  </div>
                  <div className="text-xs leading-relaxed text-white/40">{desc}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ─── FEATURES ────────────────────────────────────────────── */}
      <section id="features" className="mx-auto max-w-7xl px-6 py-24 md:px-10 lg:py-32">
        <div className="mb-14 max-w-2xl">
          <p className="text-xs uppercase tracking-[0.28em] text-cyan-400/60">Why it hits</p>
          <h2 className="mt-4 text-4xl font-bold tracking-tight md:text-5xl">
            Clean tools for messy market conditions.
          </h2>
        </div>

        <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-4">
          {features.map((f) => {
            const a = accentClasses[f.accent];
            return (
              <div
                key={f.title}
                className={`group relative overflow-hidden rounded-[1.75rem] border p-7 transition hover:-translate-y-1 hover:shadow-lg ${a.border} ${a.bg}`}
              >
                <div className={`mb-5 inline-flex h-11 w-11 items-center justify-center rounded-xl text-xl ${a.icon}`}>
                  {f.icon}
                </div>
                <h3 className="text-lg font-semibold leading-snug">{f.title}</h3>
                <p className="mt-3 text-sm leading-relaxed text-white/55">{f.text}</p>
              </div>
            );
          })}
        </div>
      </section>

      {/* ─── ACCESS / PRICING ────────────────────────────────────── */}
      <section id="access" className="border-y border-white/[0.06] bg-[#070a12]">
        <div className="mx-auto max-w-7xl px-6 py-24 md:px-10 lg:py-32">
          <div className="mb-14">
            <p className="text-xs uppercase tracking-[0.28em] text-emerald-400/60">Access</p>
            <h2 className="mt-4 max-w-3xl text-4xl font-bold tracking-tight md:text-5xl">
              Dashboard is free. Script is optional.
            </h2>
            <p className="mt-4 max-w-2xl text-lg text-white/50">
              Sign in and use the dashboard immediately. Only buy the TradingView script if you want private on-chart signals and alerts.
            </p>
          </div>

          <div className="grid gap-6 lg:grid-cols-[1.4fr_0.6fr]">
            {/* Sign-in card */}
            <div className="relative overflow-hidden rounded-[2rem] border border-white/[0.08] bg-[#0a0d18] p-8 shadow-[0_0_80px_rgba(0,224,255,0.06)] lg:p-10">
              <div className="absolute top-0 right-0 h-[300px] w-[300px] bg-cyan-400/[0.04] blur-[80px] rounded-full" />
              <div className="relative">
                <div className="mb-2 inline-flex rounded-full border border-emerald-400/20 bg-emerald-400/10 px-3 py-1 text-xs font-semibold uppercase tracking-widest text-emerald-400">
                  Free Access
                </div>
                <h3 className="mt-4 text-3xl font-bold tracking-tight md:text-4xl">Sign in to start riding.</h3>
                <p className="mt-3 max-w-lg text-base text-white/50">
                  Email/password or Google — unlock the live watchlist, alerts, options flow, and ticker tools instantly.
                </p>

                <div className="mt-8 space-y-3">
                  <input
                    type="email"
                    placeholder="Email address"
                    className="w-full rounded-xl border border-white/[0.08] bg-white/[0.03] px-5 py-3.5 text-sm text-white placeholder:text-white/20 outline-none ring-0 transition focus:border-cyan-400/30 focus:bg-white/[0.05]"
                  />
                  <input
                    type="password"
                    placeholder="Password"
                    className="w-full rounded-xl border border-white/[0.08] bg-white/[0.03] px-5 py-3.5 text-sm text-white placeholder:text-white/20 outline-none ring-0 transition focus:border-cyan-400/30 focus:bg-white/[0.05]"
                  />
                  <button className="w-full rounded-xl bg-gradient-to-r from-emerald-400 via-cyan-400 to-sky-400 py-3.5 text-sm font-bold text-black shadow-[0_0_40px_rgba(0,224,255,0.18)] transition hover:opacity-90">
                    Sign In / Create Free Account
                  </button>
                </div>

                <div className="my-6 flex items-center gap-3 text-xs text-white/20">
                  <div className="h-px flex-1 bg-white/[0.07]" />
                  <span className="tracking-widest">OR</span>
                  <div className="h-px flex-1 bg-white/[0.07]" />
                </div>

                <button className="flex w-full items-center justify-center gap-3 rounded-xl border border-white/10 bg-white px-5 py-3.5 text-sm font-semibold text-black transition hover:bg-white/90">
                  <svg className="h-5 w-5" viewBox="0 0 24 24">
                    <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                    <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                    <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
                    <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
                  </svg>
                  Continue with Google
                </button>
              </div>
            </div>

            {/* Script card */}
            <div id="script" className="rounded-[2rem] border border-emerald-400/15 bg-[#0a0d18] p-7 shadow-[0_0_60px_rgba(16,255,180,0.06)]">
              <div className="text-xs font-semibold uppercase tracking-[0.24em] text-emerald-400">Optional Add-On</div>
              <h3 className="mt-3 text-2xl font-bold tracking-tight">TradingView Script</h3>
              <p className="mt-2 text-sm text-white/45">On-chart signals, watchlist logic, and alerts — private access only.</p>

              <div className="mt-6 space-y-3">
                {[
                  { name: "Monthly", price: "$39", period: "/mo", best: false },
                  { name: "Lifetime", price: "$120", period: " once", best: true },
                ].map((plan) => (
                  <div
                    key={plan.name}
                    className={`rounded-[1.25rem] border p-5 transition hover:scale-[1.01] ${
                      plan.best
                        ? "border-emerald-400/25 bg-gradient-to-br from-emerald-400/[0.09] to-cyan-400/[0.05]"
                        : "border-white/[0.07] bg-white/[0.03]"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-xs uppercase tracking-widest text-white/40">{plan.name}</span>
                      {plan.best && (
                        <span className="rounded-full border border-emerald-400/20 bg-emerald-400/15 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-emerald-300">
                          Best Value
                        </span>
                      )}
                    </div>
                    <div className="mt-2 flex items-baseline gap-1">
                      <span className="text-3xl font-bold">{plan.price}</span>
                      <span className="text-sm text-white/35">{plan.period}</span>
                    </div>
                    <button
                      className={`mt-4 w-full rounded-xl py-2.5 text-sm font-bold transition hover:opacity-90 ${
                        plan.best
                          ? "bg-gradient-to-r from-emerald-400 to-cyan-400 text-black"
                          : "border border-white/10 bg-white/[0.05] text-white hover:bg-white/10"
                      }`}
                    >
                      {plan.best ? "Buy Lifetime Access" : "Buy Monthly"}
                    </button>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ─── BENEFITS ────────────────────────────────────────────── */}
      <section className="mx-auto max-w-7xl px-6 py-24 md:px-10 lg:py-32">
        <div className="grid gap-16 lg:grid-cols-2 lg:items-center">
          <div>
            <p className="text-xs uppercase tracking-[0.28em] text-amber-400/60">What you're really buying</p>
            <h2 className="mt-4 text-4xl font-bold tracking-tight md:text-5xl">
              Better selection. Sharper discipline.
            </h2>
            <div className="mt-6 space-y-4 text-base leading-relaxed text-white/50">
              <p>Option Riders is for traders tired of scanning aimlessly, chasing weak names, and getting dragged into setups that looked good for two seconds and then died.</p>
              <p>Focus on tradable names, cleaner context, tighter execution — a sharper daily process.</p>
            </div>
          </div>

          <div className="space-y-3">
            {[
              { text: "Know what matters before the bell", color: "amber" },
              { text: "See options flow without drowning in noise", color: "cyan" },
              { text: "Filter for tradable names with tighter spreads", color: "emerald" },
              { text: "Get dashboard and script access paths", color: "purple" },
              { text: "Trade with more structure and less emotion", color: "emerald" },
            ].map(({ text, color }, i) => (
              <div
                key={i}
                className={`flex items-center gap-4 rounded-2xl border px-5 py-4 ${
                  color === "amber" ? "border-amber-400/15 bg-amber-400/[0.04]" :
                  color === "cyan" ? "border-cyan-400/15 bg-cyan-400/[0.04]" :
                  color === "purple" ? "border-purple-400/15 bg-purple-400/[0.04]" :
                  "border-emerald-400/15 bg-emerald-400/[0.04]"
                }`}
              >
                <div className={`h-2 w-2 shrink-0 rounded-full ${
                  color === "amber" ? "bg-amber-400" :
                  color === "cyan" ? "bg-cyan-400" :
                  color === "purple" ? "bg-purple-400" :
                  "bg-emerald-400"
                }`} />
                <span className="text-sm text-white/75">{text}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ─── FAQ ─────────────────────────────────────────────────── */}
      <section id="faq" className="border-y border-white/[0.06] bg-[#070a12]">
        <div className="mx-auto max-w-4xl px-6 py-24 md:px-10 lg:py-32">
          <div className="mb-14 text-center">
            <p className="text-xs uppercase tracking-[0.28em] text-cyan-400/60">FAQ</p>
            <h2 className="mt-4 text-4xl font-bold tracking-tight md:text-5xl">Straight answers.</h2>
          </div>
          <div className="space-y-3">
            {faqs.map((faq, i) => (
              <div key={i} className="rounded-2xl border border-white/[0.07] bg-white/[0.02] p-6 transition hover:border-white/[0.12] hover:bg-white/[0.04]">
                <h3 className="font-semibold text-white">{faq.q}</h3>
                <p className="mt-2 text-sm leading-relaxed text-white/50">{faq.a}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ─── CTA ─────────────────────────────────────────────────── */}
      <section className="mx-auto max-w-7xl px-6 py-24 md:px-10 lg:py-32">
        <div className="relative overflow-hidden rounded-[2.5rem] border border-white/[0.08] bg-[#0a0d18] px-8 py-20 text-center">
          <div className="absolute inset-0 -z-10">
            <div className="absolute top-0 left-1/4 h-[300px] w-[400px] bg-cyan-500/[0.07] blur-[80px] rounded-full" />
            <div className="absolute bottom-0 right-1/4 h-[200px] w-[300px] bg-emerald-500/[0.07] blur-[80px] rounded-full" />
          </div>
          <p className="text-xs uppercase tracking-[0.28em] text-white/30">Ready to ride?</p>
          <h2 className="mx-auto mt-4 max-w-3xl text-4xl font-bold tracking-tight md:text-5xl lg:text-6xl">
            Stop forcing trades.
            <span
              className="block"
              style={{
                background: "linear-gradient(135deg, #34d399, #22d3ee)",
                WebkitBackgroundClip: "text",
                WebkitTextFillColor: "transparent",
              }}
            >
              Start trading sharp.
            </span>
          </h2>
          <p className="mx-auto mt-5 max-w-xl text-lg text-white/45">
            Start free. Add the TradingView script only if you want the extra on-chart edge.
          </p>
          <div className="mt-10 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <a
              href="#access"
              className="group flex items-center gap-2 rounded-2xl bg-gradient-to-r from-emerald-400 via-cyan-400 to-sky-400 px-8 py-4 text-base font-bold text-black shadow-[0_0_60px_rgba(0,224,255,0.25)] transition hover:scale-[1.02] hover:shadow-[0_0_80px_rgba(0,224,255,0.4)]"
            >
              Use The Free Dashboard
              <span className="transition group-hover:translate-x-1">→</span>
            </a>
            <a
              href="#dashboard"
              className="rounded-2xl border border-white/10 bg-white/[0.04] px-8 py-4 text-base font-semibold text-white/70 transition hover:bg-white/[0.08] hover:text-white"
            >
              Preview the Platform
            </a>
          </div>
        </div>
      </section>

      {/* ─── FOOTER ──────────────────────────────────────────────── */}
      <footer className="border-t border-white/[0.06] px-6 py-8 text-center text-xs text-white/25 md:px-10">
        <div className="mx-auto flex max-w-7xl items-center justify-between">
          <span className="font-semibold text-white/40">OptionRiders</span>
          <span>© 2026 OptionRiders. Built for intraday traders.</span>
          <span className="text-white/20">Trade. Ride. Profit.</span>
        </div>
      </footer>
    </div>
  );
}
