import { useCallback, useEffect, useState } from "react";
import { api, download, getToken, setToken } from "./api.js";
import { formatDate, formatSize, priorityLabel, statusLabel } from "./format.js";

function Login({ onLogged }) {
  const [mode, setMode] = useState("login");
  const [form, setForm] = useState({ email: "", full_name: "", password: "" });
  const [error, setError] = useState("");

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  async function submit(e) {
    e.preventDefault();
    setError("");
    try {
      if (mode === "register") await api.register(form.email, form.full_name, form.password);
      const { access_token } = await api.login(form.email, form.password);
      setToken(access_token);
      onLogged();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <main className="card narrow">
      <h1>Helpdesk</h1>
      <p className="muted">{mode === "login" ? "Connexion" : "Création de compte"}</p>
      <form onSubmit={submit}>
        <label>
          E-mail
          <input type="email" required value={form.email} onChange={set("email")} />
        </label>
        {mode === "register" && (
          <label>
            Nom complet
            <input required minLength={2} value={form.full_name} onChange={set("full_name")} />
          </label>
        )}
        <label>
          Mot de passe
          <input type="password" required minLength={mode === "register" ? 10 : 1} value={form.password} onChange={set("password")} />
        </label>
        {error && <p className="error">{error}</p>}
        <button type="submit">{mode === "login" ? "Se connecter" : "Créer le compte"}</button>
      </form>
      <button className="link" onClick={() => setMode(mode === "login" ? "register" : "login")}>
        {mode === "login" ? "Pas de compte ? S&apos;inscrire" : "J&apos;ai déjà un compte"}
      </button>
    </main>
  );
}

function NewTicket({ onCreated }) {
  const [form, setForm] = useState({ title: "", description: "", priority: "normal" });
  const [error, setError] = useState("");

  async function submit(e) {
    e.preventDefault();
    try {
      await api.createTicket(form);
      setForm({ title: "", description: "", priority: "normal" });
      setError("");
      onCreated();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <form className="card" onSubmit={submit}>
      <h2>Nouveau ticket</h2>
      <label>
        Titre
        <input required minLength={3} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
      </label>
      <label>
        Description
        <textarea rows={3} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
      </label>
      <label>
        Priorité
        <select value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })}>
          {["low", "normal", "high", "urgent"].map((p) => (
            <option key={p} value={p}>
              {priorityLabel(p)}
            </option>
          ))}
        </select>
      </label>
      {error && <p className="error">{error}</p>}
      <button type="submit">Créer</button>
    </form>
  );
}

function TicketDetail({ id, me, staff, onChanged }) {
  const [t, setT] = useState(null);
  const [comment, setComment] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(() => api.ticket(id).then(setT).catch((e) => setError(e.message)), [id]);
  useEffect(() => {
    load();
  }, [load]);

  if (!t) return <section className="card">{error || "Chargement…"}</section>;

  const act = (fn) => async (...a) => {
    try {
      await fn(...a);
      setError("");
      await load();
      onChanged();
    } catch (e) {
      setError(e.message);
    }
  };

  return (
    <section className="card">
      <h2>
        #{t.id} {t.title}
      </h2>
      <p className="muted">
        Par {t.author.full_name} · {formatDate(t.created_at)} · priorité {priorityLabel(t.priority)} ·{" "}
        <span className={`badge ${t.status}`}>{statusLabel(t.status)}</span>
        {t.assignee && <> · assigné à {t.assignee.full_name}</>}
      </p>
      <p>{t.description || <em>Pas de description.</em>}</p>

      {staff && (
        <div className="row">
          <select value={t.status} onChange={(e) => act(api.patchTicket)(t.id, { status: e.target.value })()}>
            {["open", "in_progress", "resolved", "closed"].map((s) => (
              <option key={s} value={s}>
                {statusLabel(s)}
              </option>
            ))}
          </select>
          <button onClick={() => act(api.patchTicket)(t.id, { assignee_id: me.id })()}>Me l&apos;assigner</button>
        </div>
      )}

      <h3>Pièces jointes</h3>
      <ul>
        {t.attachments.map((a) => (
          <li key={a.id}>
            <button className="link" onClick={() => download(`/attachments/${a.id}`, a.filename).catch((e) => setError(e.message))}>
              {a.filename}
            </button>{" "}
            <span className="muted">({formatSize(a.size)})</span>
          </li>
        ))}
        {t.attachments.length === 0 && <li className="muted">Aucune</li>}
      </ul>
      <input type="file" onChange={(e) => e.target.files[0] && act(api.upload)(t.id, e.target.files[0])()} />

      <h3>Commentaires</h3>
      {t.comments.map((c) => (
        <div key={c.id} className="comment">
          <strong>{c.author.full_name}</strong> <span className="muted">{formatDate(c.created_at)}</span>
          <div>{c.body}</div>
        </div>
      ))}
      <form
        className="row"
        onSubmit={(e) => {
          e.preventDefault();
          act(api.comment)(t.id, comment)().then(() => setComment(""));
        }}
      >
        <input required value={comment} onChange={(e) => setComment(e.target.value)} placeholder="Ajouter un commentaire" />
        <button type="submit">Envoyer</button>
      </form>
      {error && <p className="error">{error}</p>}
    </section>
  );
}

function ExportButton() {
  const [state, setState] = useState("");

  async function run() {
    setState("Export demandé…");
    const job = await api.requestExport();
    for (let i = 0; i < 30; i++) {
      await new Promise((r) => setTimeout(r, 1000));
      const s = await api.exportStatus(job.id);
      if (s.status === "done") {
        setState("Prêt");
        return download(`/exports/${job.id}/download`, `tickets_${job.id}.csv`);
      }
      if (s.status === "failed") return setState(`Échec : ${s.error}`);
    }
    setState("Toujours en cours, réessayez plus tard");
  }

  return (
    <>
      <button onClick={() => run().catch((e) => setState(e.message))}>Exporter en CSV</button> <span className="muted">{state}</span>
    </>
  );
}

function Dashboard({ me, onLogout }) {
  const [tickets, setTickets] = useState([]);
  const [filter, setFilter] = useState("");
  const [selected, setSelected] = useState(null);
  const staff = me.role === "agent" || me.role === "admin";

  const refresh = useCallback(() => api.tickets(filter).then(setTickets), [filter]);
  useEffect(() => {
    refresh();
  }, [refresh]);

  return (
    <>
      <header>
        <strong>Helpdesk</strong>
        <span>
          {me.full_name} ({me.role}) <button className="link" onClick={onLogout}>Déconnexion</button>
        </span>
      </header>
      <div className="layout">
        <div>
          <NewTicket onCreated={refresh} />
          <section className="card">
            <div className="row between">
              <h2>Tickets</h2>
              <select value={filter} onChange={(e) => setFilter(e.target.value)}>
                <option value="">Tous</option>
                {["open", "in_progress", "resolved", "closed"].map((s) => (
                  <option key={s} value={s}>
                    {statusLabel(s)}
                  </option>
                ))}
              </select>
            </div>
            <table>
              <thead>
                <tr>
                  <th>#</th>
                  <th>Titre</th>
                  <th>Priorité</th>
                  <th>Statut</th>
                </tr>
              </thead>
              <tbody>
                {tickets.map((t) => (
                  <tr key={t.id} onClick={() => setSelected(t.id)} className={selected === t.id ? "active" : ""}>
                    <td>{t.id}</td>
                    <td>{t.title}</td>
                    <td>{priorityLabel(t.priority)}</td>
                    <td>
                      <span className={`badge ${t.status}`}>{statusLabel(t.status)}</span>
                    </td>
                  </tr>
                ))}
                {tickets.length === 0 && (
                  <tr>
                    <td colSpan={4} className="muted">
                      Aucun ticket
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
            {staff && <ExportButton />}
          </section>
        </div>
        <div>{selected ? <TicketDetail key={selected} id={selected} me={me} staff={staff} onChanged={refresh} /> : <section className="card muted">Sélectionnez un ticket.</section>}</div>
      </div>
    </>
  );
}

export default function App() {
  const [me, setMe] = useState(null);
  const [ready, setReady] = useState(false);

  const loadMe = useCallback(() => {
    if (!getToken()) {
      setReady(true);
      return;
    }
    api
      .me()
      .then(setMe)
      .catch(() => setToken(null))
      .finally(() => setReady(true));
  }, []);

  useEffect(() => {
    loadMe();
  }, [loadMe]);

  if (!ready) return null;
  if (!me) return <Login onLogged={loadMe} />;
  return (
    <Dashboard
      me={me}
      onLogout={() => {
        setToken(null);
        setMe(null);
      }}
    />
  );
}
