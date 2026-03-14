import { useEffect, useState } from "react";
import Reveal from "./components/Reveal";

const workflowSteps = [
  ["Provide restaurant data", "Sales, recipes, and inventory stay scoped to one restaurant."],
  ["Weather and local events", "Demand signals are layered in before the forecast is generated."],
  ["Daily prep guidance", "Teams get a tighter prep target with less expected waste."],
] as const;

const stats = [
  { value: "Private", label: "tenant boundary" },
  { value: "3 inputs", label: "sales, weather, events" },
  { value: "Daily", label: "prep forecast output" },
] as const;

type Route = "/" | "/privacy";

function getRoute(pathname: string): Route {
  return pathname === "/privacy" ? "/privacy" : "/";
}

function NavLink({
  href,
  children,
  className,
}: {
  href: Route;
  children: string;
  className?: string;
}) {
  return (
    <a
      className={className}
      href={href}
      onClick={(event) => {
        event.preventDefault();
        window.history.pushState({}, "", href);
        window.dispatchEvent(new PopStateEvent("popstate"));
      }}
    >
      {children}
    </a>
  );
}

function HomePage() {
  return (
    <>
      <Reveal as="section" className="hero" delay={40}>
        <div className="hero-copy">
          <h1>
            <span className="hero-line">Prep closer to demand.</span>
            <span className="hero-line">Waste less.</span>
          </h1>
          <p className="lede">
            Use restaurant data, weather, and local events to plan daily prep with more confidence.
          </p>

          <div className="hero-actions">
            <a className="button button-primary" href="#workflow">
              See how it works
            </a>
            <NavLink className="button button-secondary" href="/privacy">
              Privacy
            </NavLink>
          </div>

          <div className="stat-row" aria-label="Key product facts">
            {stats.map((stat) => (
              <div className="stat-chip" key={stat.label}>
                <strong>{stat.value}</strong>
                <span>{stat.label}</span>
              </div>
            ))}
          </div>
        </div>
      </Reveal>

      <Reveal as="section" className="workflow-block" id="workflow" delay={80}>
        <h2 className="workflow-title">Three steps. One tighter plan.</h2>

        <div className="workflow-section">
          <p className="eyebrow">Workflow</p>
          <div className="workflow-grid">
            {workflowSteps.map(([title, description], index) => (
              <article className="workflow-card" key={title}>
                <span className="workflow-index">0{index + 1}</span>
                <h3>{title}</h3>
                <p>{description}</p>
              </article>
            ))}
          </div>
        </div>
      </Reveal>

      <Reveal as="aside" className="preview-panel preview-row" aria-label="Forecast preview" delay={120}>
          <div className="preview-head">
            <p>Forecast preview</p>
            <span>Today</span>
          </div>

          <div className="preview-grid">
            <article className="preview-card">
              <span className="preview-label">Weather</span>
              <strong>Rain tonight</strong>
              <p>Cooler conditions may push up dinner demand.</p>
            </article>

            <article className="preview-card">
              <span className="preview-label">Events</span>
              <strong>Arena event nearby</strong>
              <p>More foot traffic can shift demand later into the evening.</p>
            </article>

            <div className="preview-divider" aria-hidden="true">
              <span>Result</span>
            </div>

            <article className="preview-card preview-card-action">
              <span className="preview-label">Action</span>
              <strong>Prep 14% closer to expected demand</strong>
              <p>Tighten purchase and prep quantities before service.</p>
            </article>
          </div>
      </Reveal>
    </>
  );
}

function PrivacyPage() {
  return (
    <section className="privacy-page">
      <Reveal as="div" className="privacy-hero" delay={40}>
        <p className="eyebrow">Privacy</p>
        <h1>Your restaurant keeps its own data boundary.</h1>
        <p className="lede">
          Menus, sales history, and forecasts stay scoped to the restaurant using the product.
        </p>
      </Reveal>

      <Reveal as="div" className="privacy-grid" delay={80}>
        <article className="privacy-card">
          <h2>What stays private</h2>
          <p>Restaurant sales, recipes, inventory records, and forecast outputs.</p>
        </article>

        <article className="privacy-card">
          <h2>What we add</h2>
          <p>Weather and local event signals are used to improve demand planning.</p>
        </article>

        <article className="privacy-card">
          <h2>Why it matters</h2>
          <p>Restaurants should not share operational data just to get a forecast.</p>
        </article>
      </Reveal>
    </section>
  );
}

function App() {
  const [route, setRoute] = useState<Route>(() => getRoute(window.location.pathname));

  useEffect(() => {
    const handleRouteChange = () => setRoute(getRoute(window.location.pathname));

    window.addEventListener("popstate", handleRouteChange);
    return () => window.removeEventListener("popstate", handleRouteChange);
  }, []);

  return (
    <div className="page-shell">
      <header className="topbar">
        <NavLink className="brand" href="/">
          <span className="brand-mark" aria-hidden="true" />
          <span>Kitchen Forecast</span>
        </NavLink>
        <nav className="topnav" aria-label="Homepage">
          {route === "/" ? <a href="#workflow">Workflow</a> : <NavLink href="/">Home</NavLink>}
          <NavLink href="/privacy">Privacy</NavLink>
        </nav>
      </header>

      <main className="layout">{route === "/privacy" ? <PrivacyPage /> : <HomePage />}</main>
    </div>
  );
}

export default App;
