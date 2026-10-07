import { useEffect, useRef, useState } from 'react';
import { ShieldCheck, Grid2X2, Users, FileSearch, History, SlidersHorizontal, ArrowUpRight, Play, Square, Plus, Download, Upload, Check, X, Moon, Sun, Save, ChevronRight, AlertTriangle, CircleHelp, CheckCircle2, Terminal, Pencil, Trash2, LoaderCircle } from 'lucide-react';
import { api, setCSRF, downloadJSON } from './api';
import type { Project, Run, RunSummary, Bootstrap, Verdict, Account, TestCase, Result } from './types';

const labels: Record<Verdict, string> = { PASS: 'Beklenti karşılandı', VIOLATION: 'İzin ihlali', INCONCLUSIVE: 'Belirsiz', ERROR: 'Çalıştırma hatası' };
const clone = <T,>(value: T): T => JSON.parse(JSON.stringify(value));
const date = (value: string) => new Date(value).toLocaleString('tr-TR', { dateStyle: 'short', timeStyle: 'short' });
const shortId = () => crypto.randomUUID().split('-')[0];
const statusNames: Record<string, string> = { running: 'Çalışıyor', completed: 'Tamamlandı', cancelled: 'Durduruldu', interrupted: 'Yarıda kaldı', failed: 'Çalıştırma başarısız' };

function Badge({ verdict }: { verdict: Verdict }) {
  const Icon = verdict === 'PASS' ? CheckCircle2 : verdict === 'INCONCLUSIVE' ? CircleHelp : AlertTriangle;
  return <span className={`badge ${verdict.toLowerCase()}`}><Icon size={13} />{labels[verdict]}</span>;
}

export default function App() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [project, setProject] = useState<Project>();
  const [history, setHistory] = useState<RunSummary[]>([]);
  const [run, setRun] = useState<Run>();
  const [selected, setSelected] = useState<[string, string]>();
  const [view, setView] = useState('matrix');
  const [dirty, setDirty] = useState(false);
  const [isNew, setIsNew] = useState(false);
  const [snapshot, setSnapshot] = useState(false);
  const [credentialState, setCredentialState] = useState<Record<string, boolean>>({});
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [jsonText, setJsonText] = useState('');
  const [editor, setEditor] = useState<{ kind: 'account' | 'case'; index: number; text: string }>();
  const [theme, setTheme] = useState(localStorage.getItem('tenantlens-theme') || 'dark');
  const fileInput = useRef<HTMLInputElement>(null);
  const proofRef = useRef<HTMLDivElement>(null);
  const active = run?.status === 'running';

  useEffect(() => { document.documentElement.dataset.theme = theme; localStorage.setItem('tenantlens-theme', theme); }, [theme]);
  useEffect(() => {
    let cancelled = false;
    api<Bootstrap>('/api/bootstrap').then(async data => {
      if (cancelled) return;
      setCSRF(data.csrf_token); setProjects(data.projects); setHistory(data.runs); setCredentialState(data.credential_state);
      const first = data.projects.find(p => p.id === 'demo-vulnerable') || data.projects[0];
      if (first) setProject(clone(first));
      if (data.active_run) {
        const value = await api<Run>(`/api/runs/${data.active_run}`);
        if (!cancelled) { setRun(value); setProject(clone(value.project)); }
      }
    }).catch(e => !cancelled && setError(e.message)).finally(() => !cancelled && setLoading(false));
    return () => { cancelled = true; };
  }, []);
  useEffect(() => {
    if (!run || run.status !== 'running') return;
    let disposed = false;
    const timer = setInterval(() => {
      api<Run>(`/api/runs/${run.id}`).then(value => {
        if (disposed) return;
        setRun(current => current?.id === value.id ? value : current);
        if (value.status !== 'running') void reloadHistory().catch(e => !disposed && setError(e.message));
      }).catch(e => !disposed && setError(e.message));
    }, 350);
    return () => { disposed = true; clearInterval(timer); };
  }, [run?.id, run?.status]);
  useEffect(() => { if (view === 'project' && project) setJsonText(JSON.stringify(project, null, 2)); }, [view, project]);
  useEffect(() => {
    if (!editor) return;
    const escape = (event: KeyboardEvent) => { if (event.key === 'Escape') setEditor(undefined); };
    document.addEventListener('keydown', escape);
    return () => document.removeEventListener('keydown', escape);
  }, [editor]);

  async function reloadHistory() { setHistory(await api<RunSummary[]>('/api/runs')); }
  function change(next: Project) { setProject(next); setDirty(true); setRun(undefined); setSelected(undefined); setSnapshot(false); setNotice(''); }
  function choose(pid: string) {
    if (dirty && !window.confirm('Kaydedilmemiş değişiklikleri bırakıp diğer projeyi açmak istiyor musunuz?')) return;
    const next = projects.find(p => p.id === pid);
    if (next) { setProject(clone(next)); setRun(undefined); setSelected(undefined); setDirty(false); setIsNew(false); setSnapshot(false); setError(''); setNotice(''); }
  }
  async function save(): Promise<Project> {
    if (!project) throw new Error('Proje seçin.');
    const value = await api<Project>(isNew ? '/api/projects' : `/api/projects/${project.id}`, isNew ? 'POST' : 'PUT', project);
    const boot = await api<Bootstrap>('/api/bootstrap');
    setProject(value); setDirty(false); setIsNew(false); setProjects(boot.projects); setCredentialState(boot.credential_state);
    setNotice('Proje kaydedildi.'); return value;
  }
  async function action(work: () => Promise<unknown>) {
    setError(''); setNotice(''); setBusy(true);
    try { await work(); } catch (e) { setError(e instanceof Error ? e.message : 'İşlem tamamlanamadı.'); }
    finally { setBusy(false); }
  }
  async function start() {
    await action(async () => {
      const value = dirty || isNew ? await save() : project!;
      const { id } = await api<{ id: string }>(`/api/projects/${value.id}/runs`, 'POST', {});
      const next = await api<Run>(`/api/runs/${id}`); setRun(next); setSelected(undefined); setView('matrix'); setNotice(''); setSnapshot(false);
    });
  }
  function newProject() {
    if (!project) {
      const account: Account = { id: 'user-a', name: 'Kullanıcı A', tenant_id: 'org-a', roles: ['user'], auth_env: 'TENANTLENS_USER_A_TOKEN', precheck: { path: '/api/whoami', conditions: [{ pointer: '/id', equals: 'user-a' }, { pointer: '/tenant_id', equals: 'org-a' }] } };
      const next: Project = { schema_version: 1, id: 'project-' + shortId(), name: 'Yeni proje', base_url: 'http://127.0.0.1:8000', allowed_origins: ['http://127.0.0.1:8000'], settings: { timeout: 5, request_rate: 12, response_size_limit: 262144 }, accounts: [account], cases: [{ id: 'resource-a', name: 'Örnek kaynak', resource_id: 'resource-a', tenant_id: 'org-a', owner_account_id: 'user-a', method: 'GET', path: '/api/resources/resource-a', query: {}, baseline_account: 'user-a', permissions: { 'user-a': 'allow' }, success_conditions: [{ pointer: '/id', equals: 'resource-a' }], deny_statuses: [403, 404], deny_conditions: [] }] };
      change(next);
    } else { const next = clone(project); next.id = 'project-' + shortId(); next.name = 'Yeni proje'; change(next); }
    setIsNew(true); setView('project');
  }
  async function importProject(file: File) {
    await action(async () => {
      if (file.size > 1048576) throw new Error('Proje JSON dosyası 1 MiB sınırını aşıyor.');
      const value = await api<Project>('/api/validate', 'POST', JSON.parse(await file.text()));
      change(value); setIsNew(!projects.some(p => p.id === value.id)); setView('project');
      setNotice('JSON doğrulandı. Kaydet düğmesiyle projeye uygulayın.');
    });
  }
  function addAccount() {
    if (!project) return;
    const next = clone(project), id = 'user-' + shortId();
    next.accounts.push({ id, name: 'Yeni hesap', tenant_id: 'org-new', roles: ['user'], auth_env: 'TENANTLENS_' + id.replaceAll('-', '_').toUpperCase() + '_TOKEN', precheck: { path: '/api/whoami', conditions: [{ pointer: '/id', equals: id }, { pointer: '/tenant_id', equals: 'org-new' }] } });
    next.cases.forEach(c => { c.permissions[id] = 'deny'; }); change(next);
  }
  function addCase() {
    if (!project) return;
    const id = 'case-' + shortId(), first = project.accounts[0];
    const next: TestCase = { id, name: 'Yeni kaynak', resource_id: id, tenant_id: first.tenant_id, owner_account_id: first.id, method: 'GET', path: '/api/resources/' + id, query: {}, baseline_account: first.id, permissions: Object.fromEntries(project.accounts.map(a => [a.id, a.id === first.id ? 'allow' : 'deny'])), success_conditions: [{ pointer: '/id', equals: id }], deny_statuses: [403, 404], deny_conditions: [] };
    setEditor({ kind: 'case', index: -1, text: JSON.stringify(next, null, 2) });
  }
  async function applyEditor() {
    if (!editor || !project) return;
    await action(async () => {
      const value = JSON.parse(editor.text), next = clone(project);
      if (editor.kind === 'account') next.accounts[editor.index] = value;
      else if (editor.index === -1) next.cases.push(value);
      else next.cases[editor.index] = value;
      const normalized = await api<Project>('/api/validate', 'POST', next);
      change(normalized); setEditor(undefined);
    });
  }
  async function loadRun(rid: string) {
    await action(async () => {
      const value = await api<Run>(`/api/runs/${rid}`); setRun(value); setProject(clone(value.project)); setDirty(false); setIsNew(false); setSnapshot(true); setView('matrix'); setSelected(undefined);
    });
  }
  function selectCell(caseId: string, accountId: string) { setSelected([caseId, accountId]); setTimeout(() => proofRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }), 50); }
  const evidence = run?.results.find(r => selected?.[0] === r.case_id && selected?.[1] === r.account_id);
  const selectedCase = project?.cases.find(c => c.id === selected?.[0]);
  const selectedAccount = project?.accounts.find(a => a.id === selected?.[1]);
  const outstanding = run?.results.filter(r => r.verdict !== 'PASS') || [];
  const views = [{ id: 'matrix', label: 'İzin matrisi', icon: Grid2X2 }, { id: 'accounts', label: 'Hesaplar', icon: Users }, { id: 'findings', label: 'Bulgular', icon: FileSearch }, { id: 'history', label: 'Çalışma geçmişi', icon: History }, { id: 'project', label: 'Proje tanımı', icon: SlidersHorizontal }];

  if (loading) return <div className="loading"><ShieldCheck size={32} /><span>TenantLens yükleniyor…</span></div>;
  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><span className="brand-icon"><ShieldCheck size={24} /></span><div>TenantLens<small>AUTHORIZATION WORKSPACE</small></div></div>
      <div className="side-section">ÇALIŞMA ALANI</div>
      <nav aria-label="Ana gezinme">{views.map(({ id, label, icon: Icon }) => <button key={id} className={view === id ? 'nav-active' : ''} onClick={() => setView(id)}><Icon size={18} />{label}{id === 'findings' && outstanding.length > 0 && <span className="nav-count">{outstanding.length}</span>}</button>)}</nav>
      <div className="side-bottom"><div className="local-dot" /><span>Yerel çalışma alanı<small>v0.1.0 · Python + React</small></span></div>
    </aside>
    <main>
      <header className="topbar"><span>Güvenlik testleri <ChevronRight size={14} /><strong>{project?.name || 'Çalışma alanı'}</strong></span><button className="icon-button" aria-label={theme === 'dark' ? 'Açık temaya geç' : 'Koyu temaya geç'} onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}>{theme === 'dark' ? <Sun size={17} /> : <Moon size={17} />}</button></header>
      <div className="workspace">
        <div className="page-heading"><div><div className="eyebrow">API ACCESS CONTROL</div><h1>{views.find(v => v.id === view)?.label}</h1><p>Kim, hangi kaynağa erişebilir? Beklentiyi tanımlayın, kanıtla doğrulayın.</p></div><button className="button secondary" onClick={newProject} disabled={active || busy}><Plus size={16} />Yeni proje</button></div>
        {error && <div className="message error" role="alert"><AlertTriangle size={17} /><span>{error}</span><button aria-label="Hata mesajını kapat" onClick={() => setError('')}><X size={15} /></button></div>}
        {notice && <div className="message success" role="status"><Check size={17} />{notice}</div>}
        {project && <div className="project-bar"><div className="project-picker"><label htmlFor="project-select">Proje</label><select id="project-select" value={project.id} onChange={e => choose(e.target.value)} disabled={active || busy}>{isNew && <option value={project.id}>{project.name} · kaydedilmedi</option>}{projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}{snapshot && !projects.some(p => p.id === project.id) && <option value={project.id}>{project.name} · geçmiş</option>}</select></div><div className="target"><span>HEDEF ORIGIN</span><code>{project.base_url}</code></div><div className="project-actions"><button className="button quiet" onClick={() => void action(async () => { const value = await api<Project>('/api/validate', 'POST', project); downloadJSON(value, `${value.id}.json`); })} disabled={busy}><Download size={15} />JSON</button><button className="button secondary" disabled={busy || active || snapshot || (!dirty && !isNew)} onClick={() => void action(save)}><Save size={15} />Kaydet{dirty && <span className="unsaved-dot" />}</button>{active ? <button className="button danger" onClick={() => void action(() => api(`/api/runs/${run!.id}/cancel`, 'POST', {}))} disabled={busy}><Square size={14} />Durdur</button> : <button className="button primary" onClick={() => void start()} disabled={busy || snapshot}><Play size={15} />Testi çalıştır</button>}</div></div>}
        {snapshot && <div className="snapshot-banner"><History size={16} /><span>Bu çalışma, kaydedildiği andaki proje tanımıyla gösteriliyor.</span><button onClick={() => choose(project!.id)} disabled={!projects.some(p => p.id === project?.id)}>Güncel tanımı aç</button></div>}
        {view !== 'history' && view !== 'project' && project && <div className="metrics"><div><span>Matris kontrolleri</span><strong>{project.cases.length * project.accounts.length}<small>{project.accounts.length} hesap · {project.cases.length} kaynak</small></strong></div>{(['PASS', 'VIOLATION', 'INCONCLUSIVE', 'ERROR'] as Verdict[]).map(v => <div key={v} className={`metric-${v.toLowerCase()}`}><span>{labels[v]}</span><strong>{run ? run.counts[v] : '—'}<small>{run ? 'Son çalışma' : 'Henüz çalıştırılmadı'}</small></strong></div>)}</div>}
        {run && <div className="run-strip" aria-live="polite">{active ? <LoaderCircle size={14} className="spin" /> : <Terminal size={14} />}<span>{statusNames[run.status] || run.status} · {run.completed}/{run.total} kontrol · {run.request_count} HTTP isteği</span><code>{run.id.slice(0, 8)}</code>{run.status === 'failed' && <strong>Beklenmeyen motor hatası</strong>}</div>}
        {!project && view !== 'history' && <div className="empty-state"><ShieldCheck size={34} /><h2>İlk projenizi oluşturun</h2><p>Hesaplarınızı ve erişim beklentilerinizi tanımlayın veya bir proje JSON dosyası açın.</p><button className="button primary" onClick={newProject}><Plus size={15} />Yeni proje</button><button className="button secondary" onClick={() => fileInput.current?.click()}><Upload size={15} />JSON içe aktar</button></div>}
        {view === 'matrix' && project && <>
          <section className="panel"><div className="panel-heading"><div><h2>Erişim beklentileri</h2><span>Her hücre bir hesap ve kaynak için tanımlanan kuralı gösterir.</span></div><button className="button quiet" onClick={addCase} disabled={active || snapshot}><Plus size={15} />Kaynak ekle</button></div>
            <div className="table-scroll"><table className="matrix"><thead><tr><th scope="col">Kaynak / işlem</th>{project.accounts.map(a => <th scope="col" key={a.id}><strong>{a.name}</strong><span>{a.tenant_id} · {a.roles.join(', ')}</span></th>)}</tr></thead><tbody>{project.cases.map((c, ci) => <tr key={c.id}><th scope="row"><div className="resource-name">{c.name}<button className="small-icon" aria-label={`${c.name} ayrıntılarını düzenle`} disabled={active || snapshot} onClick={() => setEditor({ kind: 'case', index: ci, text: JSON.stringify(c, null, 2) })}><Pencil size={13} /></button></div><code>GET {c.path}</code><span className="baseline-note">Baseline: {project.accounts.find(a => a.id === c.baseline_account)?.name}</span></th>{project.accounts.map(a => { const value = run?.results.find(r => r.case_id === c.id && r.account_id === a.id); return <td key={a.id}><div className={`matrix-cell ${value?.verdict.toLowerCase() || ''} ${selected?.[0] === c.id && selected?.[1] === a.id ? 'selected' : ''}`}><label className="permission"><span className="sr-only">{c.name} için {a.name} beklenen erişimi</span><select aria-label={`${c.name} / ${a.name} beklenen erişim`} value={c.permissions[a.id]} disabled={active || snapshot} onChange={e => { const next = clone(project); next.cases[ci].permissions[a.id] = e.target.value as 'allow' | 'deny'; change(next); }}><option value="allow">İzinli</option><option value="deny">Yasak</option></select></label><button className="cell-result" aria-label={`${c.name} / ${a.name} kanıtını incele`} onClick={() => selectCell(c.id, a.id)}>{value ? <Badge verdict={value.verdict} /> : <span className="pending">{active ? 'Bekleniyor…' : 'Henüz çalıştırılmadı'}</span>}{value && <span className="http-status">{value.observed_status ? `HTTP ${value.observed_status}` : 'İstek değerlendirilmedi'}<ArrowUpRight size={12} /></span>}</button></div></td>; })}</tr>)}</tbody></table></div>
          </section>
          <div ref={proofRef}>{selected && selectedCase && selectedAccount ? <ProofPanel value={evidence} account={selectedAccount.name} caseName={selectedCase.name} expected={selectedCase.permissions[selectedAccount.id]} path={selectedCase.path} /> : <div className="proof-placeholder"><FileSearch size={18} /><span>Kimlik doğrulaması, baseline ve kararın kanıtını görmek için bir hücre seçin.</span></div>}</div>
        </>}
        {view === 'accounts' && project && <section className="panel"><div className="panel-heading"><div><h2>Test hesapları</h2><span>Kimlik bilgisi değerleri yerine sunucudaki ortam değişkeni referansları kullanılır.</span></div><button className="button secondary" onClick={addAccount} disabled={active || snapshot || project.accounts.length >= 12}><Plus size={15} />Hesap ekle</button></div><div className="accounts-grid">{project.accounts.map((account, index) => { const identity = run?.identities[account.id]; const locked = project.cases.some(c => c.baseline_account === account.id || c.owner_account_id === account.id); return <div className="account-card" key={account.id}><div className="account-heading"><span className="avatar">{account.name.slice(0, 1)}</span><div><strong>{account.name}</strong><code>{account.id}</code></div><span className={`credential-indicator ${identity?.verified ? 'ready' : ''}`}>{identity ? identity.verified ? 'Kimlik doğrulandı' : 'Kimlik belirsiz' : credentialState[account.auth_env] ? 'Token hazır' : 'Token bekleniyor'}</span></div><div className="account-fields">{(['name', 'tenant_id', 'auth_env'] as const).map(field => <label key={field}>{field === 'name' ? 'Hesap adı' : field === 'tenant_id' ? 'Şirket / tenant ID' : 'Token ortam değişkeni'}<input disabled={active || snapshot} value={account[field]} onChange={e => { const next = clone(project); next.accounts[index][field] = e.target.value; if (field === 'tenant_id') next.accounts[index].precheck.conditions = next.accounts[index].precheck.conditions.map(x => x.pointer === '/tenant_id' ? { ...x, equals: e.target.value } : x); change(next); }} /></label>)}<label>Roller<input disabled={active || snapshot} value={account.roles.join(', ')} onChange={e => { const next = clone(project); next.accounts[index].roles = e.target.value.split(',').map(s => s.trim()).filter(Boolean); change(next); }} /></label></div><div className="account-footer"><button className="button quiet" disabled={active || snapshot} onClick={() => setEditor({ kind: 'account', index, text: JSON.stringify(account, null, 2) })}><Pencil size={14} />Kimlik ön kontrolü</button><button className="small-icon" aria-label={`${account.name} hesabını kaldır`} disabled={active || snapshot || locked || project.accounts.length === 1} onClick={() => { const next = clone(project); next.accounts.splice(index, 1); next.cases.forEach(c => delete c.permissions[account.id]); change(next); }}><Trash2 size={15} /></button></div>{locked && <div className="field-hint">Bu hesap bir kaynağın sahibi veya baseline hesabıdır.</div>}</div>; })}</div></section>}
        {view === 'findings' && project && <section className="panel"><div className="panel-heading"><div><h2>İncelenecek sonuçlar</h2><span>İzin ihlalleri, belirsiz kontroller ve çalıştırma hataları ayrı etiketlenir.</span></div>{run && <div className="export-buttons"><a className="button secondary" href={`/api/runs/${run.id}/report.html`}><Download size={15} />HTML rapor</a><a className="button quiet" href={`/api/runs/${run.id}/report.json`}>JSON</a></div>}</div>{!run ? <Empty text="Bulguları görmek için bir test çalıştırın." /> : outstanding.length === 0 ? <Empty text="Bu çalışmada tanımlanan beklentilerin tamamı karşılandı." /> : <div className="findings">{outstanding.map(r => <button key={`${r.case_id}-${r.account_id}`} className="finding" onClick={() => { setView('matrix'); selectCell(r.case_id, r.account_id); }}><div><Badge verdict={r.verdict} /><strong>{r.account_name}<ChevronRight size={14} />{r.case_name}</strong><span>{r.reason}</span></div><ArrowUpRight size={18} /></button>)}</div>}</section>}
        {view === 'history' && <section className="panel"><div className="panel-heading"><div><h2>Kaydedilmiş çalışmalar</h2><span>Her çalışma, proje tanımının ve kanıtların ayrı bir kopyasını saklar.</span></div><button className="button quiet" onClick={() => void action(reloadHistory)}>Yenile</button></div>{history.length === 0 ? <Empty text="Henüz kaydedilmiş bir çalışma yok." /> : <div className="table-scroll"><table className="history-table"><thead><tr><th>Proje / çalışma</th><th>Zaman</th><th>Durum</th><th>Sonuçlar</th><th>İncele</th></tr></thead><tbody>{history.map(h => <tr key={h.id}><td><strong>{h.project_name}</strong><code>{h.id.slice(0, 8)}</code></td><td>{date(h.started_at)}</td><td>{statusNames[h.status] || h.status}</td><td><span className="history-counts">{h.counts.PASS} geçti · {h.counts.VIOLATION} ihlal · {h.counts.INCONCLUSIVE} belirsiz · {h.counts.ERROR} hata</span></td><td><button className="button quiet" disabled={active || busy} aria-label={`${h.id.slice(0, 8)} çalışmasını aç`} onClick={() => void loadRun(h.id)}>Aç<ArrowUpRight size={14} /></button></td></tr>)}</tbody></table></div>}</section>}
        {view === 'project' && project && <section className="panel"><div className="panel-heading"><div><h2>Proje yapılandırması</h2><span>Origin kapsamı, JSON Pointer kanıtları ve hesaplar tek bir paylaşılabilir tanımda.</span></div><button className="button secondary" onClick={() => fileInput.current?.click()} disabled={active || snapshot}><Upload size={15} />JSON içe aktar</button></div><div className="project-form"><label>Proje adı<input disabled={active || snapshot} value={project.name} onChange={e => change({ ...project, name: e.target.value })} /></label><label>Hedef origin<input disabled={active || snapshot} value={project.base_url} onChange={e => change({ ...project, base_url: e.target.value, allowed_origins: [e.target.value] })} /></label><label>İstek zaman sınırı (saniye)<input disabled={active || snapshot} type="number" min="0.1" max="30" step="0.1" value={project.settings.timeout} onChange={e => change({ ...project, settings: { ...project.settings, timeout: Number(e.target.value) } })} /></label><label>İstek hızı (istek/saniye)<input disabled={active || snapshot} type="number" min="1" max="50" value={project.settings.request_rate} onChange={e => change({ ...project, settings: { ...project.settings, request_rate: Number(e.target.value) } })} /></label></div><div className="json-editor"><label htmlFor="project-json">Gelişmiş JSON tanımı</label><textarea id="project-json" value={jsonText} disabled={active || snapshot} spellCheck={false} onChange={e => setJsonText(e.target.value)} /><div><span className="field-hint">Gerçek token değerlerini bu dosyaya yazmayın. auth_env yalnızca bir referanstır.</span><button className="button secondary" disabled={active || snapshot || busy} onClick={() => void action(async () => { const value = await api<Project>('/api/validate', 'POST', JSON.parse(jsonText)); if (value.id !== project.id) throw new Error('Mevcut proje ID değerini koruyun; yeni proje için Yeni proje düğmesini kullanın.'); change(value); setNotice('JSON doğrulandı. Değişiklikleri kaydedebilirsiniz.'); })}><Check size={15} />JSON doğrula ve uygula</button></div></div><div className="project-footer"><button className="button danger-outline" disabled={active || busy || isNew || snapshot} onClick={() => { if (window.confirm('Proje tanımını silmek istiyor musunuz? Geçmiş çalışmalar korunacak.')) void action(async () => { await api(`/api/projects/${project.id}`, 'DELETE'); const values = await api<Project[]>('/api/projects'); setProjects(values); setProject(values[0]); setDirty(false); setRun(undefined); setNotice('Proje silindi; çalışma geçmişi korundu.'); }); }}><Trash2 size={15} />Projeyi sil</button></div></section>}
        <footer className="workspace-footer"><ShieldCheck size={14} /><span>PASS, yalnızca tanımlanan kontrolün beklentiyi karşıladığını gösterir.</span></footer>
      </div>
    </main>
    <input ref={fileInput} type="file" accept=".json,application/json" className="hidden-input" aria-label="Proje JSON dosyası" onChange={e => { const file = e.target.files?.[0]; if (file) void importProject(file); e.target.value = ''; }} />
    {editor && <div className="modal-backdrop"><section className="modal" role="dialog" aria-modal="true" aria-labelledby="editor-title"><div className="panel-heading"><div><h2 id="editor-title">{editor.kind === 'case' ? 'Kaynak ve kanıt koşulları' : 'Hesap ve kimlik ön kontrolü'}</h2><span>Alanları değiştirin; tanım kaydedilmeden önce sunucuda doğrulanır.</span></div><button className="icon-button" aria-label="Düzenleyiciyi kapat" onClick={() => setEditor(undefined)}><X size={20} /></button></div><textarea autoFocus aria-label="Ayrıntılı JSON tanımı" spellCheck={false} value={editor.text} onChange={e => setEditor({ ...editor, text: e.target.value })} />{error && <div className="message error" role="alert">{error}</div>}<div className="modal-actions">{editor.kind === 'case' && editor.index >= 0 && project!.cases.length > 1 && <button className="button danger-outline" onClick={() => { const next = clone(project!); next.cases.splice(editor.index, 1); change(next); setEditor(undefined); }}><Trash2 size={14} />Kaynağı kaldır</button>}<button className="button secondary" onClick={() => setEditor(undefined)}>Vazgeç</button><button className="button primary" disabled={busy} onClick={() => void applyEditor()}><Check size={15} />Tanımı uygula</button></div></section></div>}
  </div>;
}

function Empty({ text }: { text: string }) { return <div className="empty-state compact"><FileSearch size={26} /><p>{text}</p></div>; }
function ProofPanel({ value, account, caseName, expected, path }: { value?: Result; account: string; caseName: string; expected: string; path: string }) {
  return <section className="panel proof-panel"><div className="panel-heading"><div><div className="eyebrow">TEST KANITI</div><h2>{account}<ChevronRight size={15} />{caseName}</h2></div>{value && <Badge verdict={value.verdict} />}</div><div className="proof-meta"><div><span>Beklenen erişim</span><strong>{expected === 'allow' ? 'İzinli' : 'Yasak'}</strong></div><div><span>Gözlenen HTTP yanıtı</span><strong>{value?.observed_status || '—'}</strong></div><div><span>Kimlik ön kontrolü</span><strong>{value ? value.identity_verified ? 'Doğrulandı' : 'Doğrulanamadı' : 'Bekleniyor'}</strong></div><div><span>İzinli baseline</span><strong>{value ? value.baseline_verified ? 'Doğrulandı' : 'Doğrulanamadı' : 'Bekleniyor'}</strong></div></div><div className="request-path"><code>GET {path}</code><span>{value ? `${value.elapsed_ms} ms` : ''}</span></div>{value ? <><p className="reason">{value.reason}</p>{value.evidence.length > 0 ? <div className="table-scroll"><table className="proof-table"><thead><tr><th>JSON Pointer</th><th>Beklenen değer</th><th>Gözlenen değer</th><th>Kanıt</th></tr></thead><tbody>{value.evidence.map((p, index) => <tr key={index}><td><code>{p.pointer}</code></td><td><code>{JSON.stringify(p.expected)}</code></td><td><code>{JSON.stringify(p.observed)}</code></td><td>{p.matched ? <span className="proof-match"><Check size={14} />Eşleşti</span> : <span className="proof-missing"><X size={14} />Eşleşmedi</span>}</td></tr>)}</tbody></table></div> : <div className="field-hint">Bu kontrol için hedef yanıttan başarı kanıtı toplanmadı.</div>}<div className="proof-code">Karar kodu: <code>{value.reason_code}</code></div></> : <p className="reason">Bu hücre henüz çalıştırılmadı. Testi çalıştırdığınızda gerçek API yanıtının kanıtı burada görünür.</p>}</section>;
}
