import { type ReactNode, useEffect, useMemo, useRef, useState } from 'react';
import { useSearchJobs } from '@/hooks/use-search-jobs';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ErrorBoundary } from '@/components/error-boundary';
import { Toaster } from '@/components/ui/toaster';
import { TooltipProvider } from '@/components/ui/tooltip';
import {
  ArrowUpRight,
  BarChart3,
  Bell,
  BriefcaseBusiness,
  CalendarDays,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CircleAlert,
  CircleDot,
  Database,
  Download,
  FileText,
  Heart,
  Inbox,
  LayoutDashboard,
  Lightbulb,
  ListFilter,
  Mail,
  MapPin,
  Menu,
  MessageCircleQuestion,
  MoreHorizontal,
  Pencil,
  PenLine,
  Plus,
  RotateCcw,
  Save,
  Search,
  SearchCheck,
  Send,
  Settings,
  SlidersHorizontal,
  Sparkles,
  Target,
  Trash2,
  Upload,
  X,
} from 'lucide-react';
import { Link, Route, Switch, useLocation, useParams, Router as WouterRouter } from 'wouter';
import NotFound from '@/pages/not-found';

const queryClient = new QueryClient();

type Status = 'Gesendet' | 'In Prüfung' | 'Interview' | 'Angebot' | 'Abgelehnt' | 'Entwurf';
type Application = {
  id: number; jobTitle: string; company: string; location: string; status: Status;
  appliedAt: string; via: string; match: number; salary: string; nextStep: string;
};
type Job = {
  id: number; title: string; company: string; location: string; type: string;
  salary: string; posted: string; tags: string[]; match: number; saved: boolean;
};
type Letter = { id: number; title: string; company: string; updatedAt: string; score: number; status: string };
type Question = { id: number; question: string; category: string; answer: string; feedback: string };
type Resume = {
  name: string; role: string; location: string; email: string; skills: string[];
  experience: { role: string; company: string; period: string; text: string }[];
  education: { title: string; school: string; period: string }[]; atsScore: number;
  file?: { name: string; size: number; uploadedAt: string; dataUrl?: string } | null;
};
type LocalState = {
  applications: Application[]; jobs: Job[]; letters: Letter[]; questions: Question[];
  resume: Resume; notifications: { id: number; title: string; text: string; time: string; read: boolean; type: string }[];
};

const initialState: LocalState = {
  applications: [
    { id: 1, jobTitle: 'Product Designer', company: 'Morgen Studio', location: 'Berlin · Hybrid', status: 'Interview', appliedAt: 'Heute', via: 'Unternehmensseite', match: 91, salary: '58.000 – 68.000 €', nextStep: 'Interview vorbereiten' },
    { id: 2, jobTitle: 'UX Researcher', company: 'Nunu Health', location: 'Hamburg · Hybrid', status: 'In Prüfung', appliedAt: '12. Mai 2024', via: 'LinkedIn', match: 84, salary: '55.000 – 64.000 €', nextStep: 'In 3 Tagen nachfassen' },
    { id: 3, jobTitle: 'Service Designer', company: 'Kiez & Co.', location: 'Berlin · Vor Ort', status: 'Gesendet', appliedAt: '10. Mai 2024', via: 'Empfehlung', match: 79, salary: '52.000 – 61.000 €', nextStep: 'Antwort abwarten' },
    { id: 4, jobTitle: 'Digital Strategist', company: 'Nordstern', location: 'Köln · Remote', status: 'Abgelehnt', appliedAt: '04. Mai 2024', via: 'Indeed', match: 73, salary: '60.000 – 72.000 €', nextStep: 'Reflektieren' },
    { id: 5, jobTitle: 'Brand Experience Lead', company: 'Fuchs & Partner', location: 'München · Hybrid', status: 'Angebot', appliedAt: '01. Mai 2024', via: 'Unternehmensseite', match: 88, salary: '68.000 – 78.000 €', nextStep: 'Angebot prüfen' },
  ],
  jobs: [
    { id: 11, title: 'Senior Product Designer', company: 'Hawkins & Hill', location: 'Berlin · Hybrid', type: 'Vollzeit', salary: '62.000 – 76.000 €', posted: 'vor 2 Std.', tags: ['Figma', 'Strategie', 'B2B'], match: 94, saved: true },
    { id: 12, title: 'UX Lead – Mobile', company: 'Kometenwerk', location: 'Remote · Deutschland', type: 'Vollzeit', salary: '70.000 – 84.000 €', posted: 'vor 5 Std.', tags: ['Mobile', 'Führung', 'Research'], match: 89, saved: true },
    { id: 13, title: 'Product Designer (m/w/d)', company: 'Lumen Pay', location: 'Frankfurt · Hybrid', type: 'Vollzeit', salary: '56.000 – 66.000 €', posted: 'gestern', tags: ['Fintech', 'Designsystem'], match: 86, saved: false },
    { id: 14, title: 'Design Consultant', company: 'Studio Gegenwind', location: 'Berlin · Remote', type: 'Teilzeit', salary: '48.000 – 58.000 €', posted: 'vor 2 Tagen', tags: ['Beratung', 'Workshops'], match: 81, saved: false },
  ],
  letters: [
    { id: 21, title: 'Produktdenken für Morgen Studio', company: 'Morgen Studio', updatedAt: 'Heute, 09:42', score: 92, status: 'Bereit zum Senden' },
    { id: 22, title: 'Neugier für Nunu Health', company: 'Nunu Health', updatedAt: '12. Mai 2024', score: 84, status: 'Entwurf' },
    { id: 23, title: 'Ein anderer Blick auf Kiez & Co.', company: 'Kiez & Co.', updatedAt: '08. Mai 2024', score: 77, status: 'Archiviert' },
  ],
  questions: [
    { id: 31, question: 'Erzähl uns von einem Produkt, das du von der ersten Idee bis zum Launch begleitet hast.', category: 'Erfahrung', answer: 'Bei Atlas habe ich gemeinsam mit dem Team das neue Onboarding entwickelt. Wir starteten mit fünf Gesprächen, testeten drei Varianten und konnten die Aktivierung spürbar verbessern.', feedback: 'Guter roter Faden. Ergänze noch eine konkrete Zahl und deinen persönlichen Beitrag.' },
    { id: 32, question: 'Wie gehst du vor, wenn Anforderungen noch unklar sind?', category: 'Arbeitsweise', answer: '', feedback: '' },
    { id: 33, question: 'Was war dein schwierigstes Feedback – und was hast du daraus gemacht?', category: 'Reflexion', answer: '', feedback: '' },
    { id: 34, question: 'Warum möchtest du gerade bei uns arbeiten?', category: 'Motivation', answer: '', feedback: '' },
  ],
  resume: {
    name: 'Mara Neumann', role: 'Product Designerin', location: 'Berlin, Deutschland', email: 'mara.neumann@email.de',
    skills: ['Produktstrategie', 'UX Research', 'Figma', 'Designsysteme', 'Prototyping', 'Workshop Facilitation', 'Accessibility', 'Storytelling'],
    experience: [
      { role: 'Senior Product Designerin', company: 'Atlas Digital', period: '2021 – heute', text: 'Verantwortlich für die Produktvision und das Designsystem der B2B-Plattform.' },
      { role: 'Product Designerin', company: 'Klarraum', period: '2018 – 2021', text: 'Digitale Services für eine nachhaltige Energieversorgung gestaltet.' },
    ],
    education: [{ title: 'M.A. Integrated Design', school: 'Hochschule für Künste Bremen', period: '2016 – 2018' }],
    atsScore: 82,
  },
  notifications: [
    { id: 41, title: 'Interview bei Morgen Studio', text: 'Dein Gespräch ist morgen um 10:30 Uhr.', time: 'vor 24 Min.', read: false, type: 'important' },
    { id: 42, title: 'Neue passende Stelle', text: 'Senior Product Designer bei Hawkins & Hill passt zu 94 %.', time: 'vor 2 Std.', read: false, type: 'job' },
    { id: 43, title: 'Profil-Check abgeschlossen', text: 'Deine ATS-Analyse ist bereit. Du kannst noch 3 Punkte verbessern.', time: 'gestern', read: true, type: 'insight' },
  ],
};

const navItems = [
  { href: '/', label: 'Übersicht', icon: LayoutDashboard },
  { href: '/bewerbungen', label: 'Bewerbungen', icon: BriefcaseBusiness },
  { href: '/stellen', label: 'Stellen', icon: SearchCheck },
  { href: '/lebenslauf', label: 'Lebenslauf', icon: FileText },
  { href: '/anschreiben', label: 'Anschreiben', icon: PenLine },
  { href: '/interview', label: 'Interview', icon: MessageCircleQuestion },
];

function readState(): LocalState {
  try {
    const value = localStorage.getItem('bewerbungs-workspace-state');
    if (!value) return initialState;
    const stored = JSON.parse(value) as Partial<LocalState>;
    // Deep-merge so that partial / outdated localStorage never leaves required fields undefined
    return {
      ...initialState,
      ...stored,
      resume: {
        ...initialState.resume,
        ...(stored.resume ?? {}),
        skills: Array.isArray(stored.resume?.skills) ? stored.resume.skills : initialState.resume.skills,
        experience: Array.isArray(stored.resume?.experience) ? stored.resume.experience : initialState.resume.experience,
        education: Array.isArray(stored.resume?.education) ? stored.resume.education : initialState.resume.education,
        atsScore: typeof stored.resume?.atsScore === 'number' && !isNaN(stored.resume.atsScore)
          ? stored.resume.atsScore
          : initialState.resume.atsScore,
      },
      applications: Array.isArray(stored.applications) ? stored.applications : initialState.applications,
      jobs: Array.isArray(stored.jobs) ? stored.jobs : initialState.jobs,
      letters: Array.isArray(stored.letters) ? stored.letters : initialState.letters,
      questions: Array.isArray(stored.questions) ? stored.questions : initialState.questions,
      notifications: Array.isArray(stored.notifications) ? stored.notifications : initialState.notifications,
    };
  } catch { return initialState; }
}

function useLocalState() {
  const [state, setState] = useState<LocalState>(readState);
  const [toast, setToast] = useState('');
  useEffect(() => {
    try {
      localStorage.setItem('bewerbungs-workspace-state', JSON.stringify(state));
    } catch {
      // Speicher voll (z. B. große Lebenslauf-Datei) – ohne Datei-Inhalt erneut versuchen
      try {
        const slim = { ...state, resume: { ...state.resume, file: state.resume.file ? { ...state.resume.file, dataUrl: undefined } : null } };
        localStorage.setItem('bewerbungs-workspace-state', JSON.stringify(slim));
      } catch { /* aufgeben – Zustand bleibt im Speicher der Sitzung */ }
    }
  }, [state]);
  const notify = (message: string) => {
    setToast(message);
    window.setTimeout(() => setToast(''), 2800);
  };
  return { state, setState, toast, notify };
}

function IconButton({ label, onClick, children, className = '' }: { label: string; onClick: () => void; children: ReactNode; className?: string }) {
  return <button type="button" aria-label={label} title={label} data-testid={`button-${label.toLowerCase().replaceAll(' ', '-')}`} onClick={onClick} className={`inline-flex items-center justify-center rounded-xl transition-all hover:bg-[hsl(var(--muted))] active:scale-95 ${className}`}>{children}</button>;
}

function Button({ children, onClick, variant = 'primary', type = 'button', className = '', testId = 'button-action' }: { children: ReactNode; onClick?: () => void; variant?: 'primary' | 'secondary' | 'ghost' | 'danger'; type?: 'button' | 'submit'; className?: string; testId?: string }) {
  const styles = { primary: 'bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))] shadow-[0_5px_0_hsl(12_52%_40%)] hover:-translate-y-0.5 hover:shadow-[0_7px_0_hsl(12_52%_40%)]', secondary: 'bg-[hsl(var(--secondary))] text-[hsl(var(--secondary-foreground))] hover:bg-[hsl(171_30%_85%)]', ghost: 'text-[hsl(var(--muted-foreground))] hover:bg-[hsl(var(--muted))] hover:text-[hsl(var(--foreground))]', danger: 'text-[hsl(var(--destructive))] hover:bg-[hsl(2_64%_49%_/_0.1)]' };
  return <button type={type} data-testid={testId} onClick={onClick} className={`inline-flex items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold transition-all ${styles[variant]} ${className}`}>{children}</button>;
}

function Badge({ children, tone = 'neutral' }: { children: ReactNode; tone?: 'neutral' | 'coral' | 'teal' | 'yellow' | 'red' }) {
  const tones = { neutral: 'bg-[hsl(var(--muted))] text-[hsl(var(--muted-foreground))]', coral: 'bg-[hsl(12_73%_57%_/_0.13)] text-[hsl(12_61%_43%)]', teal: 'bg-[hsl(171_30%_90%)] text-[hsl(174_35%_26%)]', yellow: 'bg-[hsl(43_87%_66%_/_0.25)] text-[hsl(37_70%_31%)]', red: 'bg-[hsl(2_64%_49%_/_0.12)] text-[hsl(2_64%_42%)]' };
  return <span className={`inline-flex items-center rounded-full px-2.5 py-1 text-[11px] font-bold tracking-wide ${tones[tone]}`}>{children}</span>;
}

function Shell({ children }: { children: ReactNode }) {
  const [location, setLocation] = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);
  const current = navItems.find(item => item.href === location)?.label ?? (location === '/einstellungen' ? 'Einstellungen' : 'Übersicht');
  return (
    <div className="noise app-shell flex bg-[hsl(var(--background))]">
      <aside className={`fixed inset-y-0 left-0 z-40 flex w-[250px] flex-col bg-[hsl(var(--sidebar))] px-4 py-5 text-[hsl(var(--sidebar-foreground))] transition-transform md:sticky md:top-0 md:translate-x-0 ${mobileOpen ? 'translate-x-0' : '-translate-x-full'}`}>
        <div className="mb-10 flex items-center gap-3 px-3">
          <div className="relative flex h-9 w-9 items-center justify-center rounded-[12px] bg-[hsl(var(--sidebar-primary))] text-[hsl(var(--sidebar-primary-foreground))]">
            <Target size={19} strokeWidth={2.5} /><span className="absolute -right-1 -top-1 h-2.5 w-2.5 rounded-full bg-[hsl(var(--accent))]" />
          </div>
          <div><div className="font-display text-[20px] font-bold tracking-tight">Nächster Schritt</div><div className="font-mono-app text-[9px] uppercase tracking-[.17em] text-[hsl(var(--sidebar-foreground)/.55)]">dein Bewerbungsraum</div></div>
        </div>
        <div className="mb-3 px-3 font-mono-app text-[10px] uppercase tracking-[.18em] text-[hsl(var(--sidebar-foreground)/.42)]">Arbeitsbereich</div>
        <nav className="space-y-1">
          {navItems.map(item => {
            const Icon = item.icon;
            const active = location === item.href;
            return <Link key={item.href} href={item.href} onClick={() => setMobileOpen(false)} data-testid={`link-${item.label.toLowerCase()}`} className={`group flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-all ${active ? 'bg-[hsl(var(--sidebar-accent))] text-[hsl(var(--sidebar-accent-foreground))]' : 'text-[hsl(var(--sidebar-foreground)/.68)] hover:bg-[hsl(var(--sidebar-accent)/.65)] hover:text-[hsl(var(--sidebar-foreground))]'}`}><Icon size={17} className={active ? 'text-[hsl(var(--sidebar-primary))]' : ''} /><span>{item.label}</span>{item.href === '/bewerbungen' && <span className="ml-auto rounded-full bg-[hsl(var(--sidebar-primary)/.18)] px-1.5 py-0.5 font-mono-app text-[10px] text-[hsl(var(--sidebar-primary))]">5</span>}</Link>;
          })}
        </nav>
        <div className="mb-3 mt-9 px-3 font-mono-app text-[10px] uppercase tracking-[.18em] text-[hsl(var(--sidebar-foreground)/.42)]">Persönlich</div>
        <nav className="space-y-1">
          <Link href="/benachrichtigungen" onClick={() => setMobileOpen(false)} data-testid="link-benachrichtigungen" className={`flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-all ${location === '/benachrichtigungen' ? 'bg-[hsl(var(--sidebar-accent))] text-[hsl(var(--sidebar-accent-foreground))]' : 'text-[hsl(var(--sidebar-foreground)/.68)] hover:bg-[hsl(var(--sidebar-accent)/.65)]'}`}><Bell size={17} /><span>Benachrichtigungen</span><span className="ml-auto h-2 w-2 rounded-full bg-[hsl(var(--sidebar-primary))]" /></Link>
          <Link href="/einstellungen" onClick={() => setMobileOpen(false)} data-testid="link-einstellungen" className={`flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-all ${location === '/einstellungen' ? 'bg-[hsl(var(--sidebar-accent))] text-[hsl(var(--sidebar-accent-foreground))]' : 'text-[hsl(var(--sidebar-foreground)/.68)] hover:bg-[hsl(var(--sidebar-accent)/.65)]'}`}><Settings size={17} /><span>Einstellungen</span></Link>
        </nav>
        <div className="mt-auto rounded-2xl border border-[hsl(var(--sidebar-border))] bg-[hsl(var(--sidebar-accent)/.55)] p-4">
          <div className="mb-2 flex items-center justify-between"><span className="font-mono-app text-[10px] uppercase tracking-wider text-[hsl(var(--sidebar-foreground)/.55)]">Wochenfokus</span><span className="font-mono-app text-[11px] text-[hsl(var(--sidebar-primary))]">68%</span></div>
          <div className="mb-3 h-1.5 overflow-hidden rounded-full bg-[hsl(var(--sidebar)/.8)]"><div className="h-full w-[68%] rounded-full bg-[hsl(var(--sidebar-primary))]" /></div>
          <p className="text-xs leading-relaxed text-[hsl(var(--sidebar-foreground)/.7)]">Noch 2 kleine Schritte, dann ist dein Profil startklar.</p>
        </div>
        <div className="mt-5 flex items-center gap-3 px-2"><div className="flex h-8 w-8 items-center justify-center rounded-full bg-[hsl(var(--accent))] font-display text-sm font-bold text-[hsl(var(--accent-foreground))]">MN</div><div className="min-w-0"><div className="truncate text-xs font-semibold">Mara Neumann</div><div className="truncate text-[11px] text-[hsl(var(--sidebar-foreground)/.5)]">Product Designerin</div></div><button type="button" data-testid="button-profil-menu" onClick={() => setLocation('/einstellungen')} className="ml-auto text-[hsl(var(--sidebar-foreground)/.45)]"><MoreHorizontal size={17} /></button></div>
      </aside>
      {mobileOpen && <button type="button" aria-label="Menü schließen" data-testid="button-close-menu" onClick={() => setMobileOpen(false)} className="fixed inset-0 z-30 bg-[hsl(217_32%_18%/.35)] md:hidden" />}
      <div className="min-w-0 flex-1">
        <header className="sticky top-0 z-20 flex h-[72px] items-center justify-between border-b border-[hsl(var(--border))] bg-[hsl(var(--background)/.88)] px-5 backdrop-blur-md md:px-10">
          <div className="flex items-center gap-3"><IconButton label="Menü öffnen" onClick={() => setMobileOpen(true)} className="h-10 w-10 md:hidden"><Menu size={19} /></IconButton><div><div className="font-mono-app text-[10px] uppercase tracking-[.18em] text-[hsl(var(--muted-foreground))]">Arbeitsbereich /</div><div className="font-display text-lg font-semibold">{current}</div></div></div>
          <div className="flex items-center gap-2"><Link href="/benachrichtigungen" data-testid="link-header-benachrichtigungen" className="relative flex h-10 w-10 items-center justify-center rounded-xl text-[hsl(var(--muted-foreground))] transition hover:bg-[hsl(var(--muted))]"><Bell size={18} /><span className="absolute right-2 top-2 h-1.5 w-1.5 rounded-full bg-[hsl(var(--primary))]" /></Link><div className="hidden h-6 w-px bg-[hsl(var(--border))] sm:block" /><div className="hidden items-center gap-2 text-xs font-medium sm:flex"><span className="font-mono-app text-[hsl(var(--muted-foreground))]">DI, 14. MAI</span><span className="h-1.5 w-1.5 rounded-full bg-[hsl(var(--accent))]" /></div></div>
        </header>
        <main className="page-enter mx-auto w-full max-w-[1440px] px-5 py-7 pb-28 md:px-10 md:py-10 md:pb-12">{children}</main>
      </div>
      <nav className="fixed bottom-0 left-0 right-0 z-30 flex h-[68px] items-center justify-around border-t border-[hsl(var(--border))] bg-[hsl(var(--card)/.96)] px-2 backdrop-blur-md md:hidden">
        {navItems.slice(0, 5).map(item => { const Icon = item.icon; return <Link key={item.href} href={item.href} data-testid={`mobile-link-${item.label.toLowerCase()}`} className={`flex flex-col items-center gap-1 px-2 py-1 text-[10px] font-semibold ${location === item.href ? 'text-[hsl(var(--primary))]' : 'text-[hsl(var(--muted-foreground))]'}`}><Icon size={18} /><span>{item.label}</span></Link>; })}
      </nav>
    </div>
  );
}

function PageHeading({ eyebrow, title, description, action }: { eyebrow?: string; title: string; description?: string; action?: ReactNode }) {
  return <div className="mb-8 flex flex-col justify-between gap-5 sm:flex-row sm:items-end"><div><div className="mb-2 font-mono-app text-[10px] uppercase tracking-[.2em] text-[hsl(var(--primary))]">{eyebrow}</div><h1 className="font-display text-[clamp(2rem,4vw,3.35rem)] font-semibold leading-[.98] tracking-[-.045em] text-[hsl(var(--foreground))]">{title}</h1>{description && <p className="mt-3 max-w-xl text-sm leading-6 text-[hsl(var(--muted-foreground))]">{description}</p>}</div>{action && <div className="shrink-0">{action}</div>}</div>;
}

function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <section className={`rounded-2xl border border-[hsl(var(--card-border))] bg-[hsl(var(--card))] shadow-[0_10px_28px_hsl(35_35%_30%/.035)] ${className}`}>{children}</section>;
}

function ProgressBar({ value, color = 'primary' }: { value: number; color?: 'primary' | 'teal' | 'yellow' | 'coral' }) {
  const bg = color === 'teal' ? 'bg-[hsl(171_45%_42%)]' : color === 'yellow' ? 'bg-[hsl(43_82%_52%)]' : 'bg-[hsl(var(--primary))]';
  return <div className="h-2 overflow-hidden rounded-full bg-[hsl(var(--muted))]"><div className={`h-full rounded-full ${bg} transition-all duration-500`} style={{ width: `${value}%` }} /></div>;
}

function Toast({ message }: { message: string }) {
  if (!message) return null;
  return <div role="status" data-testid="status-toast" className="fixed bottom-24 right-5 z-[60] flex items-center gap-2 rounded-xl bg-[hsl(var(--sidebar))] px-4 py-3 text-sm font-semibold text-[hsl(var(--sidebar-foreground))] shadow-xl md:bottom-6 md:right-8"><CheckCircle2 size={17} className="text-[hsl(var(--sidebar-primary))]" />{message}</div>;
}

function Dashboard({ state, notify }: { state: LocalState; notify: (message: string) => void }) {
  const [, setLocation] = useLocation();
  const open = state.applications.filter(a => !['Abgelehnt', 'Angebot'].includes(a.status)).length;
  const interview = state.applications.filter(a => a.status === 'Interview').length;
  const tasks = [{ title: 'Interview bei Morgen Studio vorbereiten', meta: 'Morgen, 10:30 Uhr', icon: MessageCircleQuestion, tone: 'coral' }, { title: 'Bei Nunu Health nachfassen', meta: 'Fällig in 3 Tagen', icon: Send, tone: 'teal' }, { title: 'ATS-Analyse vervollständigen', meta: '3 Hinweise offen', icon: SearchCheck, tone: 'yellow' }];
  return <div className="space-y-7">
    <div className="flex flex-col justify-between gap-5 lg:flex-row lg:items-end"><div className="reveal"><div className="mb-2 flex items-center gap-2 font-mono-app text-[10px] uppercase tracking-[.2em] text-[hsl(var(--primary))]"><span className="h-2 w-2 rounded-full bg-[hsl(var(--primary))]" />Dienstag, 14. Mai 2024</div><h1 className="font-display text-[clamp(2.5rem,5vw,4.5rem)] font-semibold leading-[.88] tracking-[-.06em]">Guten Morgen,<br /><span className="text-[hsl(var(--primary))]">Mara.</span></h1><p className="mt-5 max-w-md text-[15px] leading-6 text-[hsl(var(--muted-foreground))]">Du bist gut unterwegs. Heute reicht ein klarer, kleiner Schritt.</p></div><div className="reveal reveal-delay-1 flex gap-3"><Button onClick={() => setLocation('/bewerbungen')} testId="button-quick-application"><Plus size={17} />Bewerbung hinzufügen</Button><Button variant="secondary" onClick={() => setLocation('/stellen')} testId="button-quick-jobs"><Search size={17} />Stellen entdecken</Button></div></div>
    <div className="grid gap-5 lg:grid-cols-[1.45fr_.8fr_.8fr]">
      <Card className="reveal reveal-delay-1 relative overflow-hidden bg-[hsl(var(--sidebar))] p-6 text-[hsl(var(--sidebar-foreground))] sm:p-7"><div className="absolute -right-12 -top-16 h-44 w-44 rounded-full border-[18px] border-[hsl(var(--sidebar-primary)/.14)]" /><div className="absolute -right-2 top-4 h-24 w-24 rounded-full border border-[hsl(var(--accent)/.45)]" /><div className="relative flex h-full flex-col justify-between"><div><div className="mb-7 flex items-center justify-between"><span className="font-mono-app text-[10px] uppercase tracking-[.18em] text-[hsl(var(--sidebar-foreground)/.6)]">Dein Wochenrhythmus</span><span className="rounded-full border border-[hsl(var(--sidebar-border))] px-2 py-1 font-mono-app text-[10px] text-[hsl(var(--sidebar-primary))]">KW 20</span></div><div className="mb-2 font-display text-4xl font-semibold">68<span className="text-2xl text-[hsl(var(--sidebar-foreground)/.4)]">%</span></div><p className="max-w-[230px] text-sm leading-5 text-[hsl(var(--sidebar-foreground)/.65)]">deines Wochenfokus geschafft. Das Wichtigste ist bereits in Bewegung.</p></div><div className="mt-8"><div className="mb-2 flex justify-between text-[11px] text-[hsl(var(--sidebar-foreground)/.55)]"><span>Montag</span><span>Sonntag</span></div><div className="h-2 overflow-hidden rounded-full bg-[hsl(var(--sidebar)/.85)]"><div className="h-full w-[68%] rounded-full bg-[hsl(var(--sidebar-primary))]" /></div></div></div></Card>
      <Card className="reveal reveal-delay-2 p-6"><div className="mb-7 flex items-center justify-between"><span className="font-mono-app text-[10px] uppercase tracking-[.16em] text-[hsl(var(--muted-foreground))]">Aktive Bewerbungen</span><BriefcaseBusiness size={18} className="text-[hsl(var(--primary))]" /></div><div className="font-display text-4xl font-semibold">{open}</div><div className="mt-3 flex items-center gap-1.5 text-xs text-[hsl(171_45%_35%)]"><ArrowUpRight size={14} />2 seit letzter Woche</div><div className="mt-7 border-t border-[hsl(var(--border))] pt-4 text-xs text-[hsl(var(--muted-foreground))]">5 insgesamt verfolgt</div></Card>
      <Card className="reveal reveal-delay-3 p-6"><div className="mb-7 flex items-center justify-between"><span className="font-mono-app text-[10px] uppercase tracking-[.16em] text-[hsl(var(--muted-foreground))]">Gespräche</span><MessageCircleQuestion size={18} className="text-[hsl(171_45%_35%)]" /></div><div className="font-display text-4xl font-semibold">{interview}</div><div className="mt-3 flex items-center gap-1.5 text-xs text-[hsl(var(--muted-foreground))]"><CalendarDays size={14} />nächster Termin morgen</div><div className="mt-7 border-t border-[hsl(var(--border))] pt-4 text-xs text-[hsl(var(--muted-foreground))]">Du bist vorbereitet</div></Card>
    </div>
    <div className="grid gap-5 xl:grid-cols-[1.15fr_.85fr]">
      <Card className="reveal p-6 sm:p-7"><div className="mb-6 flex items-start justify-between"><div><div className="mb-1 font-mono-app text-[10px] uppercase tracking-[.16em] text-[hsl(var(--muted-foreground))]">Heute im Fokus</div><h2 className="font-display text-2xl font-semibold">Deine nächsten Schritte</h2></div><Link href="/bewerbungen" data-testid="link-all-tasks" className="flex items-center gap-1 text-xs font-semibold text-[hsl(var(--primary))]">Alle anzeigen <ChevronRight size={14} /></Link></div><div className="space-y-2">{tasks.map((task, index) => { const Icon = task.icon; return <button type="button" key={task.title} data-testid={`task-${index}`} onClick={() => notify('Schritt als erledigt markiert')} className="group flex w-full items-center gap-4 rounded-xl border border-transparent p-3 text-left transition hover:border-[hsl(var(--border))] hover:bg-[hsl(var(--background))]"><div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${task.tone === 'coral' ? 'bg-[hsl(12_73%_57%_/.13)] text-[hsl(var(--primary))]' : task.tone === 'teal' ? 'bg-[hsl(var(--secondary))] text-[hsl(174_35%_26%)]' : 'bg-[hsl(var(--accent)/.23)] text-[hsl(37_70%_31%)]'}`}><Icon size={18} /></div><div className="min-w-0 flex-1"><div className="truncate text-sm font-semibold">{task.title}</div><div className="mt-1 text-xs text-[hsl(var(--muted-foreground))]">{task.meta}</div></div><CircleDot size={17} className="text-[hsl(var(--border))] transition group-hover:text-[hsl(var(--primary))]" /></button>; })}</div></Card>
      <Card className="reveal reveal-delay-1 p-6 sm:p-7"><div className="mb-7 flex items-start justify-between"><div><div className="mb-1 font-mono-app text-[10px] uppercase tracking-[.16em] text-[hsl(var(--muted-foreground))]">Dein Verlauf</div><h2 className="font-display text-2xl font-semibold">Bewerbungsbewegung</h2></div><BarChart3 size={19} className="text-[hsl(var(--primary))]" /></div><div className="flex h-36 items-end gap-2 border-b border-[hsl(var(--border))] pb-0">{[32, 46, 38, 68, 58, 82, 74, 91, 65, 78, 87, 100].map((height, index) => <div key={index} className="group flex h-full flex-1 items-end"><div className={`w-full rounded-t-[4px] transition-all duration-300 group-hover:bg-[hsl(var(--primary))] ${index === 11 ? 'bg-[hsl(var(--primary))]' : 'bg-[hsl(12_73%_57%/.24)]'}`} style={{ height: `${height}%` }} /></div>)}</div><div className="mt-3 flex justify-between font-mono-app text-[9px] uppercase tracking-wide text-[hsl(var(--muted-foreground))]"><span>KW 10</span><span>KW 15</span><span>Diese Woche</span></div><div className="mt-7 flex items-center gap-3 rounded-xl bg-[hsl(var(--secondary)/.6)] p-3 text-xs leading-5 text-[hsl(var(--secondary-foreground))]"><Lightbulb size={16} className="shrink-0" />Dienstag ist dein produktivster Tag. Gute Gelegenheit für eine neue Bewerbung.</div></Card>
    </div>
    <Card className="reveal p-6 sm:p-7"><div className="mb-5 flex items-center justify-between"><div><div className="mb-1 font-mono-app text-[10px] uppercase tracking-[.16em] text-[hsl(var(--muted-foreground))]">Zuletzt passiert</div><h2 className="font-display text-2xl font-semibold">Aktivität</h2></div><button type="button" data-testid="button-activity-filter" onClick={() => notify('Aktivität ist bereits aktuell')} className="text-xs font-semibold text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--primary))]">Diese Woche <ChevronDown size={14} className="ml-1 inline" /></button></div><div className="grid gap-3 md:grid-cols-3">{[['Heute, 09:42', 'Anschreiben aktualisiert', 'Morgen Studio · Score 92', 'coral'], ['Gestern, 16:18', 'Stelle gespeichert', 'Senior Product Designer · 94 % Match', 'teal'], ['Montag, 11:05', 'Interview-Antwort ergänzt', 'Erfahrung · Feedback erhalten', 'yellow']].map(([time, title, detail, tone], i) => <div key={i} data-testid={`activity-${i}`} className="flex gap-3 border-l-2 border-[hsl(var(--border))] pl-4"><div className={`mt-1 h-2 w-2 shrink-0 rounded-full ${tone === 'coral' ? 'bg-[hsl(var(--primary))]' : tone === 'teal' ? 'bg-[hsl(171_45%_42%)]' : 'bg-[hsl(43_82%_52%)]'}`} /><div><div className="font-mono-app text-[10px] text-[hsl(var(--muted-foreground))]">{time}</div><div className="mt-1 text-sm font-semibold">{title}</div><div className="mt-1 text-xs text-[hsl(var(--muted-foreground))]">{detail}</div></div></div>)}</div></Card>
  </div>;
}

function ApplicationsPage({ state, setState, notify }: { state: LocalState; setState: React.Dispatch<React.SetStateAction<LocalState>>; notify: (message: string) => void }) {
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('Alle');
  const [showModal, setShowModal] = useState(false);
  const [form, setForm] = useState({ jobTitle: '', company: '', location: '', salary: '', status: 'Gesendet' as Status, via: 'Unternehmensseite' });
  const filtered = useMemo(() => state.applications.filter(a => (statusFilter === 'Alle' || a.status === statusFilter) && `${a.jobTitle} ${a.company}`.toLowerCase().includes(search.toLowerCase())), [state.applications, search, statusFilter]);
  const updateStatus = (id: number, status: Status) => { setState(s => ({ ...s, applications: s.applications.map(a => a.id === id ? { ...a, status } : a) })); notify('Status aktualisiert'); };
  const remove = (id: number) => { if (window.confirm('Diese Bewerbung wirklich löschen?')) { setState(s => ({ ...s, applications: s.applications.filter(a => a.id !== id) })); notify('Bewerbung gelöscht'); } };
  const submit = (event: React.FormEvent) => { event.preventDefault(); if (!form.jobTitle || !form.company) return; setState(s => ({ ...s, applications: [{ ...form, id: Date.now(), appliedAt: 'Heute', match: 80, nextStep: 'Antwort abwarten' }, ...s.applications] })); setForm({ jobTitle: '', company: '', location: '', salary: '', status: 'Gesendet', via: 'Unternehmensseite' }); setShowModal(false); notify('Bewerbung hinzugefügt'); };
  return <div className="space-y-7"><PageHeading eyebrow="Verfolgung" title="Bewerbungen" description="Alles, was du angestoßen hast – an einem Ort, ohne den Überblick zu verlieren." action={<Button onClick={() => setShowModal(true)} testId="button-new-application"><Plus size={17} />Neue Bewerbung</Button>} />
    <div className="grid gap-3 sm:grid-cols-4"><StatMini label="Gesamt" value={state.applications.length} /><StatMini label="In Prüfung" value={state.applications.filter(a => a.status === 'In Prüfung').length} tone="teal" /><StatMini label="Interviews" value={state.applications.filter(a => a.status === 'Interview').length} tone="yellow" /><StatMini label="Angebote" value={state.applications.filter(a => a.status === 'Angebot').length} tone="coral" /></div>
    <Card className="overflow-hidden"><div className="flex flex-col gap-3 border-b border-[hsl(var(--border))] p-4 md:flex-row md:items-center"><div className="relative flex-1"><Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-[hsl(var(--muted-foreground))]" /><input data-testid="input-search-applications" value={search} onChange={e => setSearch(e.target.value)} placeholder="Bewerbungen durchsuchen …" className="h-10 w-full rounded-xl border border-[hsl(var(--border))] bg-[hsl(var(--background))] pl-9 pr-3 text-sm outline-none transition focus:border-[hsl(var(--primary))] focus:ring-1 focus:ring-[hsl(var(--primary)/.25)] placeholder:text-[hsl(var(--muted-foreground))]" /></div><div className="flex items-center gap-2"><ListFilter size={16} className="text-[hsl(var(--muted-foreground))]" /><select data-testid="select-application-status" value={statusFilter} onChange={e => setStatusFilter(e.target.value)} className="h-10 rounded-xl border border-[hsl(var(--border))] bg-[hsl(var(--card))] px-3 text-sm outline-none"><option>Alle</option>{(['Gesendet', 'In Prüfung', 'Interview', 'Angebot', 'Abgelehnt', 'Entwurf'] as Status[]).map(s => <option key={s}>{s}</option>)}</select></div></div><div className="hidden grid-cols-[1.7fr_1fr_.8fr_.8fr_1.2fr_36px] gap-4 border-b border-[hsl(var(--border))] bg-[hsl(var(--background)/.6)] px-6 py-3 font-mono-app text-[10px] uppercase tracking-wider text-[hsl(var(--muted-foreground))] lg:grid"><span>Position</span><span>Status</span><span>Match</span><span>Datum</span><span>Nächster Schritt</span><span /></div><div className="divide-y divide-[hsl(var(--border))]">{filtered.map(app => <ApplicationRow key={app.id} app={app} onStatus={updateStatus} onDelete={remove} />)}</div>{filtered.length === 0 && <EmptyState icon={<Inbox size={22} />} title="Keine Bewerbungen gefunden" text="Versuche einen anderen Suchbegriff oder lege eine neue Bewerbung an." action={<Button onClick={() => setShowModal(true)}>Bewerbung anlegen</Button>} />}</Card>
    {showModal && <Modal title="Neue Bewerbung" onClose={() => setShowModal(false)}><form onSubmit={submit} className="space-y-4"><Field label="Jobtitel" required value={form.jobTitle} onChange={v => setForm({ ...form, jobTitle: v })} placeholder="z. B. Product Designer" /><Field label="Unternehmen" required value={form.company} onChange={v => setForm({ ...form, company: v })} placeholder="z. B. Studio Gegenwind" /><div className="grid gap-4 sm:grid-cols-2"><Field label="Ort & Arbeitsmodell" value={form.location} onChange={v => setForm({ ...form, location: v })} placeholder="Berlin · Hybrid" /><Field label="Gehalt" value={form.salary} onChange={v => setForm({ ...form, salary: v })} placeholder="55.000 – 65.000 €" /></div><div className="grid gap-4 sm:grid-cols-2"><SelectField label="Status" value={form.status} onChange={v => setForm({ ...form, status: v as Status })} options={['Gesendet', 'In Prüfung', 'Interview', 'Entwurf']} /><SelectField label="Über" value={form.via} onChange={v => setForm({ ...form, via: v })} options={['Unternehmensseite', 'LinkedIn', 'Empfehlung', 'Indeed']} /></div><div className="flex justify-end gap-2 pt-3"><Button variant="ghost" onClick={() => setShowModal(false)}>Abbrechen</Button><Button type="submit" testId="button-submit-application"><Plus size={16} />Hinzufügen</Button></div></form></Modal>}</div>;
}

function StatMini({ label, value, tone = 'coral' }: { label: string; value: number; tone?: 'coral' | 'teal' | 'yellow' }) { return <Card className="flex items-center justify-between px-5 py-4"><span className="text-xs font-medium text-[hsl(var(--muted-foreground))]">{label}</span><span className={`font-display text-2xl font-semibold ${tone === 'teal' ? 'text-[hsl(171_45%_35%)]' : tone === 'yellow' ? 'text-[hsl(37_70%_31%)]' : 'text-[hsl(var(--primary))]'}`}>{value}</span></Card>; }

function ApplicationRow({ app, onStatus, onDelete }: { app: Application; onStatus: (id: number, status: Status) => void; onDelete: (id: number) => void }) {
  const [editing, setEditing] = useState(false);
  const tone = app.status === 'Interview' || app.status === 'Angebot' ? 'teal' : app.status === 'Abgelehnt' ? 'red' : app.status === 'In Prüfung' ? 'yellow' : 'coral';
  return <div data-testid={`row-application-${app.id}`} className="grid gap-3 px-4 py-4 transition hover:bg-[hsl(var(--background)/.6)] md:px-6 lg:grid-cols-[1.7fr_1fr_.8fr_.8fr_1.2fr_36px] lg:items-center"><div className="flex min-w-0 items-center gap-3"><div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[hsl(var(--secondary))] font-display text-sm font-bold text-[hsl(var(--secondary-foreground))]">{app.company.slice(0, 1)}</div><div className="min-w-0"><div className="truncate text-sm font-semibold">{app.jobTitle}</div><div className="mt-1 flex items-center gap-2 text-xs text-[hsl(var(--muted-foreground))]"><span>{app.company}</span><span className="h-1 w-1 rounded-full bg-[hsl(var(--border))]" /><span>{app.location}</span></div></div></div><div className="flex items-center justify-between lg:block">{editing ? <select autoFocus data-testid={`select-status-${app.id}`} value={app.status} onChange={e => { onStatus(app.id, e.target.value as Status); setEditing(false); }} onBlur={() => setEditing(false)} className="rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--card))] px-2 py-1 text-xs"><option>Gesendet</option><option>In Prüfung</option><option>Interview</option><option>Angebot</option><option>Abgelehnt</option><option>Entwurf</option></select> : <button type="button" data-testid={`button-edit-status-${app.id}`} onClick={() => setEditing(true)}><Badge tone={tone}>{app.status}<ChevronDown size={12} className="ml-1" /></Badge></button>}</div><div className="flex items-center gap-2 text-sm font-semibold lg:block"><span className="lg:hidden text-xs text-[hsl(var(--muted-foreground))]">Match</span><span className={app.match >= 85 ? 'text-[hsl(171_45%_35%)]' : 'text-[hsl(var(--foreground))]'}>{app.match} %</span></div><div className="hidden text-xs text-[hsl(var(--muted-foreground))] lg:block">{app.appliedAt}</div><div className="hidden text-xs text-[hsl(var(--muted-foreground))] lg:block">{app.nextStep}</div><IconButton label="Bewerbung löschen" onClick={() => onDelete(app.id)} className="h-9 w-9 text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--destructive))]"><Trash2 size={15} /></IconButton></div>;
}

const JOB_BOARDS = [
  {
    id: 'jobboerse',
    label: 'Jobbörse',
    sublabel: 'Bundesagentur für Arbeit',
    color: '#005FA3',
    logo: 'JB',
    url: (q: string) => `https://www.arbeitsagentur.de/jobsuche/suche?angebotsart=1&was=${encodeURIComponent(q || 'Product Designer')}&wo=Deutschland`,
  },
  {
    id: 'indeed',
    label: 'Indeed',
    sublabel: 'Millionen Stellenangebote',
    color: '#2164f3',
    logo: 'In',
    url: (q: string) => `https://de.indeed.com/jobs?q=${encodeURIComponent(q || 'Product Designer')}&l=Deutschland`,
  },
  {
    id: 'stepstone',
    label: 'StepStone',
    sublabel: 'Deutschlands Jobmarkt',
    color: '#e5001a',
    logo: 'SS',
    url: (q: string) => `https://www.stepstone.de/jobs/${encodeURIComponent((q || 'product-designer').toLowerCase().replace(/\s+/g, '-'))}/`,
  },
] as const;

function parseJobPaste(text: string): Partial<Job> {
  const lines = text.split('\n').map(l => l.trim()).filter(Boolean);
  const title = lines[0] ?? '';
  const companyLine = lines.find(l => /GmbH|AG|SE|KG|Co\.|Studios?|Labs?|Gruppe|Group|UG/i.test(l) && l !== title) ?? lines[1] ?? '';
  const locationLine = lines.find(l => /Berlin|Hamburg|München|Köln|Frankfurt|Stuttgart|Düsseldorf|Remote|hybrid|vor Ort/i.test(l)) ?? '';
  const salaryLine = lines.find(l => /€|\d{2,}[.,]\d{3}/.test(l)) ?? '';
  const tagCandidates = lines.filter(l => l.length < 30 && !/€|\d{2,3}\.000/.test(l) && l !== title && l !== companyLine && l !== locationLine).slice(0, 4);
  return {
    title,
    company: companyLine,
    location: locationLine || 'Nicht angegeben',
    salary: salaryLine || 'Nicht angegeben',
    tags: tagCandidates,
    type: 'Vollzeit',
    posted: 'Manuell importiert',
    match: 80,
    saved: false,
  };
}

function ImportModal({ onClose, onImport }: { onClose: () => void; onImport: (job: Job, target: 'application' | 'job') => void }) {
  const [text, setText] = useState('');
  const [preview, setPreview] = useState<Partial<Job> | null>(null);
  const handleParse = () => setPreview(parseJobPaste(text));
  const built = (): Job => ({ ...preview, id: Date.now() } as Job);
  return (
    <Modal title="Stelle importieren" onClose={onClose}>
      <div className="space-y-4">
        <p className="text-sm leading-6 text-[hsl(var(--muted-foreground))]">
          Kopiere den Text einer Stellenanzeige (z. B. von Indeed oder StepStone) und füge ihn hier ein. Titel, Unternehmen, Ort und Gehalt werden automatisch erkannt.
        </p>
        <label className="block text-xs font-semibold">
          Anzeigentext einfügen
          <textarea
            data-testid="textarea-import-job"
            value={text}
            onChange={e => { setText(e.target.value); setPreview(null); }}
            rows={8}
            placeholder={'Senior Product Designer\nMorgen Studio GmbH\nBerlin · Hybrid\n58.000 – 68.000 €\nFigma, Strategie, B2B\n...'}
            className="mt-2 w-full resize-none rounded-xl border border-[hsl(var(--border))] bg-[hsl(var(--background))] p-3 font-mono-app text-xs leading-6 outline-none transition focus:border-[hsl(var(--primary))]"
          />
        </label>
        {!preview && (
          <Button onClick={handleParse} variant="secondary" testId="button-parse-job" className="w-full">
            <Search size={16} />Erkennen
          </Button>
        )}
        {preview && (
          <div className="rounded-xl border border-[hsl(var(--border))] bg-[hsl(var(--background))] p-4 space-y-3 text-sm">
            <div className="font-semibold text-base">{preview.title || <span className="text-[hsl(var(--muted-foreground))]">Kein Titel erkannt</span>}</div>
            <div className="text-[hsl(var(--muted-foreground))] text-xs space-y-1">
              <div><span className="font-semibold text-[hsl(var(--foreground))]">Unternehmen:</span> {preview.company}</div>
              <div><span className="font-semibold text-[hsl(var(--foreground))]">Ort:</span> {preview.location}</div>
              <div><span className="font-semibold text-[hsl(var(--foreground))]">Gehalt:</span> {preview.salary}</div>
              {(preview.tags ?? []).length > 0 && (
                <div className="flex flex-wrap gap-1 mt-2">
                  {(preview.tags ?? []).map(t => <span key={t} className="rounded-md bg-[hsl(var(--muted))] px-2 py-0.5 text-[10px] font-medium">{t}</span>)}
                </div>
              )}
            </div>
            <div className="border-t border-[hsl(var(--border))] pt-3 text-xs text-[hsl(var(--muted-foreground))]">Wohin soll die Stelle?</div>
            <div className="grid gap-2 sm:grid-cols-2">
              <button
                type="button"
                data-testid="button-import-as-application"
                onClick={() => { if (preview.title) onImport(built(), 'application'); }}
                className="flex flex-col items-start gap-1 rounded-xl border-2 border-[hsl(var(--primary))] bg-[hsl(12_73%_57%/.06)] p-3 text-left transition hover:bg-[hsl(12_73%_57%/.12)]"
              >
                <span className="flex items-center gap-1.5 font-semibold text-[hsl(var(--primary))]"><BriefcaseBusiness size={15} />Als Bewerbung anlegen</span>
                <span className="text-[11px] text-[hsl(var(--muted-foreground))]">Erscheint direkt in deiner Bewerbungsliste als Entwurf</span>
              </button>
              <button
                type="button"
                data-testid="button-import-as-job"
                onClick={() => { if (preview.title) onImport(built(), 'job'); }}
                className="flex flex-col items-start gap-1 rounded-xl border border-[hsl(var(--border))] bg-[hsl(var(--background))] p-3 text-left transition hover:border-[hsl(var(--primary)/.4)] hover:bg-[hsl(var(--muted)/.4)]"
              >
                <span className="flex items-center gap-1.5 font-semibold"><Heart size={15} />Als Stelle merken</span>
                <span className="text-[11px] text-[hsl(var(--muted-foreground))]">Wird unter gespeicherte Stellen abgelegt</span>
              </button>
            </div>
            <Button variant="ghost" onClick={() => setPreview(null)} className="w-full text-xs">Nochmal bearbeiten</Button>
          </div>
        )}
      </div>
    </Modal>
  );
}

type ExternalJob = { id: string; title: string; company: string; location: string; url: string; source: string; salary?: string | null; posted: string; description?: string | null };

function JobsPage({ state, setState, notify }: { state: LocalState; setState: React.Dispatch<React.SetStateAction<LocalState>>; notify: (message: string) => void }) {
  const [search, setSearch] = useState('');
  const [location, setLocation] = useState('');
  const [radius, setRadius] = useState(25);
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [debouncedLocation, setDebouncedLocation] = useState('');
  const [onlySaved, setOnlySaved] = useState(false);
  const [showImport, setShowImport] = useState(false);

  // Debounce: Suche erst nach 600 ms senden
  useEffect(() => {
    const id = window.setTimeout(() => { setDebouncedSearch(search); setDebouncedLocation(location); }, 600);
    return () => window.clearTimeout(id);
  }, [search, location]);

  // Echte Suche über Backend (Adzuna + Arbeitnow)
  const trimmedLocation = debouncedLocation.trim();
  const { data: arbeitnowJobs, isLoading: isSearchingArbeitnow } = useSearchJobs(
    { q: debouncedSearch, ...(trimmedLocation ? { l: trimmedLocation, radius } : {}) },
    { query: { queryKey: ['searchJobs', debouncedSearch, trimmedLocation, radius], enabled: debouncedSearch.trim().length >= 2 } },
  );

  // BA Jobbörse – direkt aus dem Browser (die öffentliche Jobsuche-API der Arbeitsagentur)
  const [baJobs, setBaJobs] = useState<ExternalJob[] | null>(null);
  const [isSearchingBa, setIsSearchingBa] = useState(false);
  const [baBlocked, setBaBlocked] = useState(false);
  useEffect(() => {
    const q = debouncedSearch.trim();
    if (q.length < 2) { setBaJobs(null); setBaBlocked(false); return; }
    let cancelled = false;
    setIsSearchingBa(true);
    setBaBlocked(false);
    fetch(`https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobs?was=${encodeURIComponent(q)}&size=15`, {
      headers: { 'X-API-Key': 'jobboerse-jobsuche' },
    })
      .then(res => (res.ok ? res.json() : Promise.reject(new Error(`HTTP ${res.status}`))))
      .then((data: { stellenangebote?: { refnr?: string; titel?: string; beruf?: string; arbeitgeber?: string; arbeitsort?: { ort?: string; region?: string }; aktuelleVeroeffentlichungsdatum?: string; externeUrl?: string }[] }) => {
        if (cancelled) return;
        const mapped: ExternalJob[] = (data.stellenangebote ?? []).map((s, i) => ({
          id: `ba-${s.refnr ?? i}`,
          title: s.titel || s.beruf || 'Stellenangebot',
          company: s.arbeitgeber || '',
          location: [s.arbeitsort?.ort, s.arbeitsort?.region].filter(Boolean).join(', '),
          url: s.externeUrl || (s.refnr ? `https://www.arbeitsagentur.de/jobsuche/jobdetail/${encodeURIComponent(s.refnr)}` : 'https://www.arbeitsagentur.de/jobsuche/'),
          source: 'BA Jobbörse',
          salary: null,
          posted: s.aktuelleVeroeffentlichungsdatum ? new Date(s.aktuelleVeroeffentlichungsdatum).toLocaleDateString('de-DE') : '',
          description: null,
        }));
        setBaJobs(mapped);
      })
      .catch(() => { if (!cancelled) { setBaJobs([]); setBaBlocked(true); } })
      .finally(() => { if (!cancelled) setIsSearchingBa(false); });
    return () => { cancelled = true; };
  }, [debouncedSearch]);

  const isSearching = isSearchingArbeitnow || isSearchingBa;
  const externalJobs = useMemo<ExternalJob[]>(() => [...(baJobs ?? []), ...((arbeitnowJobs as ExternalJob[] | undefined) ?? [])], [baJobs, arbeitnowJobs]);

  // Lokale gespeicherte Stellen
  const filtered = useMemo(() => state.jobs.filter(j =>
    (!onlySaved || j.saved) &&
    `${j.title} ${j.company} ${j.tags.join(' ')}`.toLowerCase().includes(search.toLowerCase())
  ), [state.jobs, search, onlySaved]);

  const toggleSaved = (id: number) => {
    setState(s => ({ ...s, jobs: s.jobs.map(j => j.id === id ? { ...j, saved: !j.saved } : j) }));
    notify('Gespeicherte Stellen aktualisiert');
  };
  const takeOver = (job: Job) => {
    setState(s => ({ ...s, applications: [{ id: Date.now(), jobTitle: job.title, company: job.company, location: job.location, status: 'Entwurf', appliedAt: 'Heute', via: 'Nächster Schritt', match: job.match, salary: job.salary, nextStep: 'Bewerbung vorbereiten' }, ...s.applications] }));
    notify('Stelle in Bewerbungen übernommen');
  };
  const importJob = (job: Job, target: 'application' | 'job') => {
    if (target === 'application') {
      setState(s => ({ ...s, applications: [{ id: Date.now(), jobTitle: job.title, company: job.company || 'Unbekannt', location: job.location || '', status: 'Entwurf', appliedAt: 'Heute', via: 'Import', match: 80, salary: job.salary || '', nextStep: 'Bewerbung vorbereiten' }, ...s.applications] }));
      notify('Bewerbung angelegt – du findest sie unter Bewerbungen');
    } else {
      setState(s => ({ ...s, jobs: [job, ...s.jobs] }));
      notify('Stelle gespeichert');
    }
    setShowImport(false);
  };
  const applyExternal = (ext: ExternalJob) => {
    setState(s => ({ ...s, applications: [{ id: Date.now(), jobTitle: ext.title, company: ext.company || 'Unbekannt', location: ext.location || '', status: 'Entwurf', appliedAt: 'Heute', via: ext.source, match: 80, salary: ext.salary || '', nextStep: 'Bewerbung vorbereiten' }, ...s.applications] }));
    notify('Bewerbung angelegt – du findest sie unter Bewerbungen');
  };
  const saveExternal = (ext: ExternalJob) => {
    const job: Job = { id: Date.now(), title: ext.title, company: ext.company || '', location: ext.location || '', type: 'Vollzeit', salary: ext.salary || '', posted: ext.posted, tags: [], match: 80, saved: true };
    setState(s => ({ ...s, jobs: [job, ...s.jobs] }));
    notify('Stelle gespeichert');
  };

  return (
    <div className="space-y-7">
      <PageHeading
        eyebrow="Entdecken"
        title="Stellen"
        description="Suche direkt in Stellenbörsen – Ergebnisse erscheinen inline. Anzeige kopieren und per Import als Bewerbung anlegen."
        action={<Button onClick={() => setShowImport(true)} testId="button-import-job"><Plus size={17} />Stelle importieren</Button>}
      />

      {/* Suchzeile */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-[240px] flex-1">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-[hsl(var(--muted-foreground))]" />
          <input
            data-testid="input-search-jobs"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Jobtitel oder Skill eingeben …"
            className="h-11 w-full rounded-xl border border-[hsl(var(--border))] bg-[hsl(var(--card))] pl-9 pr-3 text-sm outline-none transition focus:border-[hsl(var(--primary))] focus:ring-1 focus:ring-[hsl(var(--primary)/.25)]"
          />
        </div>
        <div className="relative min-w-[160px]">
          <MapPin size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-[hsl(var(--muted-foreground))]" />
          <input
            data-testid="input-search-location"
            value={location}
            onChange={e => setLocation(e.target.value)}
            placeholder="Ort / PLZ"
            className="h-11 w-full rounded-xl border border-[hsl(var(--border))] bg-[hsl(var(--card))] pl-9 pr-3 text-sm outline-none transition focus:border-[hsl(var(--primary))] focus:ring-1 focus:ring-[hsl(var(--primary)/.25)]"
          />
        </div>
        <select
          data-testid="select-search-radius"
          value={radius}
          onChange={e => setRadius(Number(e.target.value))}
          disabled={!location.trim()}
          aria-label="Umkreis"
          className="h-11 rounded-xl border border-[hsl(var(--border))] bg-[hsl(var(--card))] px-3 text-sm font-semibold text-[hsl(var(--foreground))] outline-none transition focus:border-[hsl(var(--primary))] disabled:opacity-50"
        >
          <option value={5}>+ 5 km</option>
          <option value={10}>+ 10 km</option>
          <option value={25}>+ 25 km</option>
          <option value={50}>+ 50 km</option>
          <option value={100}>+ 100 km</option>
        </select>
        {/* Externe Boards – öffnen im Browser */}
        <button type="button" data-testid="button-open-jobboerse"
          onClick={() => window.open(`https://www.arbeitsagentur.de/jobsuche/suche?angebotsart=1&was=${encodeURIComponent(search || 'Designer')}&wo=Deutschland`, '_blank', 'noopener,noreferrer')}
          className="flex h-11 items-center gap-2 rounded-xl border border-[hsl(var(--border))] bg-[hsl(var(--card))] px-4 text-sm font-semibold text-[hsl(var(--muted-foreground))] transition hover:text-[hsl(var(--foreground))]"
        >
          <span className="flex h-5 w-5 items-center justify-center rounded-md bg-[#005FA3] text-[9px] font-bold text-white">JB</span>
          Jobbörse <ArrowUpRight size={14} />
        </button>
        <button type="button" data-testid="button-open-stepstone"
          onClick={() => window.open(`https://www.stepstone.de/jobs/${encodeURIComponent((search || 'product-designer').toLowerCase().replace(/\s+/g, '-'))}/`, '_blank', 'noopener,noreferrer')}
          className="flex h-11 items-center gap-2 rounded-xl border border-[hsl(var(--border))] bg-[hsl(var(--card))] px-4 text-sm font-semibold text-[hsl(var(--muted-foreground))] transition hover:text-[hsl(var(--foreground))]"
        >
          <span className="flex h-5 w-5 items-center justify-center rounded-md bg-[#e5001a] text-[9px] font-bold text-white">SS</span>
          StepStone <ArrowUpRight size={14} />
        </button>
        <Button variant={onlySaved ? 'primary' : 'ghost'} onClick={() => setOnlySaved(!onlySaved)} testId="button-filter-saved">
          <Heart size={16} fill={onlySaved ? 'currentColor' : 'none'} />Gespeichert
        </Button>
      </div>

      {/* Inline-Suchergebnisse (Arbeitnow) */}
      {debouncedSearch.trim().length >= 2 && (
        <div>
          <div className="mb-4 flex items-center justify-between">
            <h2 className="font-display text-xl font-semibold">
              Suchergebnisse
              <span className="ml-2 font-mono-app text-sm font-normal text-[hsl(var(--muted-foreground))]">
                {isSearching ? 'Wird geladen …' : `${externalJobs?.length ?? 0} Treffer`}
              </span>
            </h2>
          </div>
          {baBlocked && !isSearching && (
            <div data-testid="banner-ba-blocked" className="mb-4 flex flex-wrap items-center gap-3 rounded-xl border border-[hsl(var(--border))] bg-[hsl(var(--muted)/.6)] px-4 py-3 text-sm text-[hsl(var(--muted-foreground))]">
              <CircleAlert size={16} className="shrink-0 text-[hsl(43_82%_45%)]" />
              <span className="flex-1">
                <span className="font-semibold text-[hsl(var(--foreground))]">BA Jobbörse nicht erreichbar.</span>
                {' '}Die direkte API-Abfrage wurde vom Browser blockiert (CORS). Ergebnisse von anderen Quellen werden angezeigt.
              </span>
              <button
                type="button"
                onClick={() => window.open(`https://www.arbeitsagentur.de/jobsuche/suche?angebotsart=1&was=${encodeURIComponent(debouncedSearch)}&wo=Deutschland`, '_blank', 'noopener,noreferrer')}
                className="flex items-center gap-1.5 rounded-lg bg-[#005FA3] px-3 py-1.5 text-xs font-semibold text-white transition hover:opacity-90"
              >
                <span className="font-bold">JB</span> BA Jobbörse öffnen <ArrowUpRight size={13} />
              </button>
            </div>
          )}
          {isSearching ? (
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {[1, 2, 3].map(i => (
                <Card key={i} className="p-5 space-y-3">
                  <div className="h-5 w-2/3 animate-pulse rounded-lg bg-[hsl(var(--muted))]" />
                  <div className="h-4 w-1/2 animate-pulse rounded-lg bg-[hsl(var(--muted))]" />
                  <div className="h-4 w-3/4 animate-pulse rounded-lg bg-[hsl(var(--muted))]" />
                </Card>
              ))}
            </div>
          ) : externalJobs && externalJobs.length > 0 ? (
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {externalJobs.map((ext) => (
                <Card key={ext.id} className="group flex flex-col p-5 transition hover:-translate-y-1 hover:shadow-[0_14px_32px_hsl(35_35%_30%/.09)]">
                  <div className="mb-4 flex items-start justify-between gap-2">
                    <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-[hsl(var(--sidebar))] font-display text-lg font-bold text-[hsl(var(--sidebar-foreground))]">
                      {(ext.company || ext.title).slice(0, 1).toUpperCase()}
                    </div>
                    <span className="rounded-full border border-[hsl(var(--border))] bg-[hsl(var(--background))] px-2 py-0.5 font-mono-app text-[10px] text-[hsl(var(--muted-foreground))]">{ext.source}</span>
                  </div>
                  {ext.company && <div className="mb-1 font-mono-app text-[10px] uppercase tracking-wider text-[hsl(var(--muted-foreground))]">{ext.company}</div>}
                  <h3 className="font-display text-lg font-semibold leading-tight">{ext.title}</h3>
                  <div className="mt-2 space-y-1 text-xs text-[hsl(var(--muted-foreground))]">
                    {ext.location && <div className="flex items-center gap-2"><MapPin size={13} />{ext.location}</div>}
                    {ext.salary && <div className="flex items-center gap-2"><BriefcaseBusiness size={13} />{ext.salary}</div>}
                  </div>
                  {ext.description && <p className="mt-3 line-clamp-2 text-xs leading-5 text-[hsl(var(--muted-foreground))]">{ext.description}</p>}
                  <div className="mt-auto flex items-center justify-between border-t border-[hsl(var(--border))] pt-4 mt-5">
                    <span className="font-mono-app text-[10px] text-[hsl(var(--muted-foreground))]">{ext.posted}</span>
                    <div className="flex items-center gap-1">
                      <button type="button" data-testid={`button-save-external-${ext.id}`} onClick={() => saveExternal(ext)} className="flex items-center gap-1 rounded-lg px-2 py-1.5 text-xs text-[hsl(var(--muted-foreground))] transition hover:bg-[hsl(var(--muted))] hover:text-[hsl(var(--foreground))]"><Heart size={13} />Merken</button>
                      <button type="button" data-testid={`button-apply-external-${ext.id}`} onClick={() => applyExternal(ext)} className="flex items-center gap-1 rounded-lg bg-[hsl(var(--primary))] px-3 py-1.5 text-xs font-semibold text-[hsl(var(--primary-foreground))] transition hover:opacity-90"><Plus size={13} />Bewerben</button>
                      <a href={ext.url} target="_blank" rel="noopener noreferrer" data-testid={`link-external-${ext.id}`} className="flex items-center gap-1 rounded-lg px-2 py-1.5 text-xs text-[hsl(var(--muted-foreground))] transition hover:bg-[hsl(var(--muted))]"><ArrowUpRight size={13} /></a>
                    </div>
                  </div>
                </Card>
              ))}
            </div>
          ) : (
            <Card className="p-6 sm:p-8">
              <EmptyState
                icon={<Search size={22} />}
                title="Keine Ergebnisse"
                text={`Für „${debouncedSearch}" wurden keine internationalen Stellenangebote gefunden. Für deutsche Berufsfelder (Pflege, Handwerk, Verwaltung …) direkt auf der BA Jobbörse suchen:`}
              />
              <div className="mt-4 flex justify-center gap-3">
                <button type="button"
                  onClick={() => window.open(`https://www.arbeitsagentur.de/jobsuche/suche?angebotsart=1&was=${encodeURIComponent(debouncedSearch)}&wo=Deutschland`, '_blank', 'noopener,noreferrer')}
                  className="flex items-center gap-2 rounded-xl bg-[#005FA3] px-4 py-2.5 text-sm font-semibold text-white transition hover:opacity-90"
                >
                  <span className="text-xs font-bold">JB</span> BA Jobbörse öffnen <ArrowUpRight size={14} />
                </button>
                <button type="button"
                  onClick={() => window.open(`https://www.stepstone.de/jobs/${encodeURIComponent(debouncedSearch.toLowerCase().replace(/\s+/g, '-'))}/`, '_blank', 'noopener,noreferrer')}
                  className="flex items-center gap-2 rounded-xl border border-[hsl(var(--border))] bg-[hsl(var(--background))] px-4 py-2.5 text-sm font-semibold transition hover:bg-[hsl(var(--muted))]"
                >
                  StepStone öffnen <ArrowUpRight size={14} />
                </button>
              </div>
            </Card>
          )}
        </div>
      )}

      {/* Gespeicherte Stellen */}
      {filtered.length > 0 && (
        <div>
          <h2 className="mb-4 font-display text-xl font-semibold">Gespeicherte Stellen <span className="ml-2 font-mono-app text-sm font-normal text-[hsl(var(--muted-foreground))]">{filtered.length}</span></h2>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {filtered.map(job => <JobCard key={job.id} job={job} onSave={toggleSaved} onTakeOver={takeOver} />)}
          </div>
        </div>
      )}
      {filtered.length === 0 && debouncedSearch.trim().length < 2 && (
        <Card><EmptyState icon={<Search size={22} />} title="Bereit zum Suchen" text="Gib oben mindestens 2 Zeichen ein – die Ergebnisse von Indeed oder der BA Jobbörse erscheinen direkt hier." action={<Button onClick={() => setShowImport(true)}>Stelle importieren</Button>} /></Card>
      )}

      {showImport && <ImportModal onClose={() => setShowImport(false)} onImport={importJob} />}
    </div>
  );
}

function JobCard({ job, onSave, onTakeOver }: { job: Job; onSave: (id: number) => void; onTakeOver: (job: Job) => void }) {
  return <Card className="group relative flex flex-col p-5 transition hover:-translate-y-1 hover:shadow-[0_14px_32px_hsl(35_35%_30%/.09)]"><div className="mb-5 flex items-start justify-between"><div className="flex h-11 w-11 items-center justify-center rounded-xl bg-[hsl(var(--sidebar))] font-display text-lg font-bold text-[hsl(var(--sidebar-foreground))]">{job.company.slice(0, 1)}</div><div className="flex items-center gap-1"><Badge tone="teal">{job.match} % Match</Badge><IconButton label="Stelle speichern" onClick={() => onSave(job.id)} className={job.saved ? 'h-9 w-9 text-[hsl(var(--primary))]' : 'h-9 w-9 text-[hsl(var(--muted-foreground))]'}><Heart size={17} fill={job.saved ? 'currentColor' : 'none'} /></IconButton></div></div><div className="mb-1 font-mono-app text-[10px] uppercase tracking-wider text-[hsl(var(--muted-foreground))]">{job.company}</div><h3 className="font-display text-xl font-semibold leading-tight">{job.title}</h3><div className="mt-3 space-y-2 text-xs text-[hsl(var(--muted-foreground))]"><div className="flex items-center gap-2"><MapPin size={14} />{job.location}</div><div className="flex items-center gap-2"><BriefcaseBusiness size={14} />{job.type} · {job.salary}</div></div><div className="mt-5 flex flex-wrap gap-1.5">{job.tags.map(tag => <span key={tag} className="rounded-md bg-[hsl(var(--muted))] px-2 py-1 text-[10px] font-medium text-[hsl(var(--muted-foreground))]">{tag}</span>)}</div><div className="mt-6 flex items-center justify-between border-t border-[hsl(var(--border))] pt-4"><span className="font-mono-app text-[10px] text-[hsl(var(--muted-foreground))]">{job.posted}</span><Button variant="ghost" onClick={() => onTakeOver(job)} className="px-2 py-1.5 text-xs" testId={`button-takeover-job-${job.id}`}>Übernehmen <ArrowUpRight size={14} /></Button></div></Card>;
}

// hint: Structural and logic conflict. Both design and behavior differ.
function ResumePage({ state, setState, notify }: { state: LocalState; setState: React.Dispatch<React.SetStateAction<LocalState>>; notify: (message: string) => void }) {
  const [tab, setTab] = useState<'profil' | 'analyse'>('profil'); const [uploading, setUploading] = useState(false); const resume = state.resume;
  const update = (key: keyof Resume, value: string) => setState(s => ({ ...s, resume: { ...s.resume, [key]: value } }));
  const uploadTokenRef = useRef(0);
  const upload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    const token = ++uploadTokenRef.current;
    setUploading(true);
    const finish = (dataUrl?: string) => {
      if (token !== uploadTokenRef.current) return; // eine neuere Auswahl hat Vorrang
      setState(s => ({ ...s, resume: { ...s.resume, atsScore: Math.min(99, s.resume.atsScore + 3), file: { name: file.name, size: file.size, uploadedAt: new Date().toLocaleDateString('de-DE'), dataUrl } } }));
      setUploading(false);
      notify('Lebenslauf hochgeladen – Profil aktualisiert');
    };
    if (file.size <= 2 * 1024 * 1024) {
      const reader = new FileReader();
      reader.onload = () => finish(typeof reader.result === 'string' ? reader.result : undefined);
      reader.onerror = () => finish(undefined);
      reader.readAsDataURL(file);
    } else {
      finish(undefined);
      notify('Datei ist größer als 2 MB – nur Dateiname gespeichert');
    }
  };
  return <div className="space-y-7"><PageHeading eyebrow="Dein Profil" title="Lebenslauf" description="Ein lebendiges Profil, das mit jeder Bewerbung stärker wird." action={<label data-testid="button-upload-resume" className="inline-flex cursor-pointer items-center gap-2 rounded-xl bg-[hsl(var(--primary))] px-4 py-2.5 text-sm font-semibold text-[hsl(var(--primary-foreground))] shadow-[0_5px_0_hsl(12_52%_40%)] transition hover:-translate-y-0.5"><Upload size={17} />{uploading ? 'Wird analysiert …' : 'Datei hochladen'}<input type="file" accept=".pdf,.doc,.docx" className="hidden" onChange={upload} /></label>} />{resume.file && <Card className="flex flex-wrap items-center gap-4 p-5" data-testid="card-uploaded-resume"><div className="flex h-11 w-11 items-center justify-center rounded-xl bg-[hsl(var(--primary)/.12)] text-[hsl(var(--primary))]"><FileText size={20} /></div><div className="min-w-0 flex-1"><div className="truncate font-semibold" data-testid="text-resume-filename">{resume.file.name}</div><div className="font-mono-app text-[10px] text-[hsl(var(--muted-foreground))]">Hochgeladen am {resume.file.uploadedAt} · {(resume.file.size / 1024).toFixed(0)} KB</div></div><div className="flex items-center gap-2">{resume.file.dataUrl && <a href={resume.file.dataUrl} download={resume.file.name} data-testid="button-download-resume" className="flex items-center gap-1.5 rounded-lg border border-[hsl(var(--border))] px-3 py-2 text-xs font-semibold transition hover:bg-[hsl(var(--muted))]"><Download size={14} />Herunterladen</a>}<button type="button" data-testid="button-remove-resume-file" onClick={() => { setState(s => ({ ...s, resume: { ...s.resume, file: null } })); notify('Datei entfernt'); }} className="flex items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-semibold text-[hsl(var(--muted-foreground))] transition hover:bg-[hsl(var(--muted))] hover:text-[hsl(var(--foreground))]"><X size={14} />Entfernen</button></div></Card>}<div className="flex gap-1 border-b border-[hsl(var(--border))]"><TabButton active={tab === 'profil'} onClick={() => setTab('profil')} label="Profil & Inhalt" testId="tab-resume-profile" /><TabButton active={tab === 'analyse'} onClick={() => setTab('analyse')} label="ATS-Analyse" testId="tab-resume-analysis" /></div>{tab === 'profil' ? <div className="grid gap-5 xl:grid-cols-[1.2fr_.8fr]"><Card className="p-6 sm:p-8"><div className="mb-7 flex items-start justify-between"><div><div className="mb-1 font-mono-app text-[10px] uppercase tracking-[.16em] text-[hsl(var(--muted-foreground))]">Persönliche Angaben</div><h2 className="font-display text-2xl font-semibold">So darf man dich kennenlernen</h2></div><Pencil size={17} className="text-[hsl(var(--muted-foreground))]" /></div><div className="grid gap-4 sm:grid-cols-2"><Field label="Name" value={resume.name} onChange={v => update('name', v)} /><Field label="Berufsbezeichnung" value={resume.role} onChange={v => update('role', v)} /><Field label="Standort" value={resume.location} onChange={v => update('location', v)} /><Field label="E-Mail" value={resume.email} onChange={v => update('email', v)} /></div><div className="mt-8 flex justify-end"><Button onClick={() => notify('Profil gespeichert')} testId="button-save-resume"><Save size={16} />Änderungen speichern</Button></div></Card><Card className="p-6 sm:p-8"><div className="mb-6 flex items-center justify-between"><div><div className="mb-1 font-mono-app text-[10px] uppercase tracking-[.16em] text-[hsl(var(--muted-foreground))]">Relevanz</div><h2 className="font-display text-2xl font-semibold">Deine Skills</h2></div><Badge tone="teal">{resume.skills.length} Skills</Badge></div><div className="flex flex-wrap gap-2">{resume.skills.map(skill => <span key={skill} className="group inline-flex items-center gap-1.5 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))] px-3 py-2 text-xs font-semibold">{skill}<button type="button" aria-label={`${skill} entfernen`} data-testid={`button-remove-skill-${skill}`} onClick={() => setState(s => ({ ...s, resume: { ...s.resume, skills: s.resume.skills.filter(item => item !== skill) } }))} className="text-[hsl(var(--muted-foreground))] opacity-0 transition group-hover:opacity-100"><X size={12} /></button></span>)}</div><button type="button" data-testid="button-add-skill" onClick={() => { const skill = window.prompt('Welchen Skill möchtest du ergänzen?'); if (skill) { setState(s => ({ ...s, resume: { ...s.resume, skills: [...s.resume.skills, skill] } })); notify('Skill ergänzt'); } }} className="mt-5 flex items-center gap-2 text-xs font-semibold text-[hsl(var(--primary))]"><Plus size={15} />Skill ergänzen</button></Card><Card className="p-6 sm:p-8 xl:col-span-2"><div className="mb-6 flex items-center justify-between"><div><div className="mb-1 font-mono-app text-[10px] uppercase tracking-[.16em] text-[hsl(var(--muted-foreground))]">Stationen</div><h2 className="font-display text-2xl font-semibold">Erfahrung & Ausbildung</h2></div><Button variant="ghost" onClick={() => notify('Bearbeitung für Stationen geöffnet')} testId="button-edit-experience"><Pencil size={15} />Bearbeiten</Button></div><div className="grid gap-8 md:grid-cols-2"><div className="space-y-5">{resume.experience.map((item, i) => <div key={i} className="relative border-l-2 border-[hsl(var(--primary)/.35)] pl-5"><div className="absolute -left-[7px] top-0 h-3 w-3 rounded-full border-2 border-[hsl(var(--card))] bg-[hsl(var(--primary))]" /><div className="font-mono-app text-[10px] text-[hsl(var(--primary))]">{item.period}</div><div className="mt-1 font-semibold">{item.role}</div><div className="text-sm text-[hsl(var(--muted-foreground))]">{item.company}</div><p className="mt-2 text-xs leading-5 text-[hsl(var(--muted-foreground))]">{item.text}</p></div>)}</div><div className="space-y-5">{resume.education.map((item, i) => <div key={i} className="relative border-l-2 border-[hsl(171_45%_42%/.35)] pl-5"><div className="absolute -left-[7px] top-0 h-3 w-3 rounded-full border-2 border-[hsl(var(--card))] bg-[hsl(171_45%_42%)]" /><div className="font-mono-app text-[10px] text-[hsl(171_45%_35%)]">{item.period}</div><div className="mt-1 font-semibold">{item.title}</div><div className="text-sm text-[hsl(var(--muted-foreground))]">{item.school}</div></div>)}</div></div></Card></div> : <div className="grid gap-5 lg:grid-cols-[.7fr_1.3fr]"><Card className="p-7"><div className="flex items-center gap-5"><div className="relative flex h-32 w-32 items-center justify-center rounded-full" style={{ background: `conic-gradient(hsl(var(--primary)) ${resume.atsScore * 3.6}deg, hsl(var(--muted)) 0deg)` }}><div className="flex h-24 w-24 flex-col items-center justify-center rounded-full bg-[hsl(var(--card))]"><span className="font-display text-4xl font-semibold">{resume.atsScore}</span><span className="font-mono-app text-[9px] uppercase text-[hsl(var(--muted-foreground))]">von 100</span></div></div><div><Badge tone="teal">Gut aufgestellt</Badge><p className="mt-3 text-sm leading-5 text-[hsl(var(--muted-foreground))]">Dein Profil wird von den meisten ATS-Systemen gut gelesen.</p></div></div><div className="mt-7 border-t border-[hsl(var(--border))] pt-5 text-xs leading-5 text-[hsl(var(--muted-foreground))]">Ein paar gezielte Anpassungen machen dich noch sichtbarer.</div></Card><Card className="p-7"><div className="mb-7"><div className="mb-1 font-mono-app text-[10px] uppercase tracking-[.16em] text-[hsl(var(--muted-foreground))]">Chancen</div><h2 className="font-display text-2xl font-semibold">Drei gute Verbesserungen</h2></div><div className="space-y-5"><AnalysisItem title="Messbare Wirkung ergänzen" text="In 2 Stationen fehlen konkrete Ergebnisse oder Kennzahlen." value={72} color="yellow" /><AnalysisItem title="Skills priorisieren" text="„Accessibility“ und „Research“ passen besonders gut zu deinen Zielrollen." value={86} color="teal" /><AnalysisItem title="Profil-Link hinzufügen" text="Ein Link zu deinem Portfolio schafft zusätzliches Vertrauen." value={55} color="coral" /></div><Button variant="secondary" onClick={() => notify('Analyse-Hinweise als erledigt markiert')} className="mt-7" testId="button-apply-analysis"><Check size={16} />Hinweise prüfen</Button></Card></div>}</div>;
}

function AnalysisItem({ title, text, value, color }: { title: string; text: string; value: number; color: 'yellow' | 'teal' | 'coral' }) { return <div><div className="mb-2 flex items-center justify-between"><span className="text-sm font-semibold">{title}</span><span className="font-mono-app text-[10px] text-[hsl(var(--muted-foreground))]">{value}%</span></div><ProgressBar value={value} color={color} /><p className="mt-2 text-xs leading-5 text-[hsl(var(--muted-foreground))]">{text}</p></div>; }

function LettersPage({ state, setState, notify }: { state: LocalState; setState: React.Dispatch<React.SetStateAction<LocalState>>; notify: (message: string) => void }) {
  const [showModal, setShowModal] = useState(false); const [editing, setEditing] = useState<Letter | null>(null);
  const add = () => { const letter: Letter = { id: Date.now(), title: 'Neuer Entwurf', company: 'Noch kein Unternehmen', updatedAt: 'Gerade eben', score: 0, status: 'Entwurf' }; setState(s => ({ ...s, letters: [letter, ...s.letters] })); setEditing(letter); setShowModal(false); notify('Neuer Entwurf gestartet'); };
  const remove = (id: number) => { if (window.confirm('Diesen Entwurf löschen?')) { setState(s => ({ ...s, letters: s.letters.filter(l => l.id !== id) })); notify('Entwurf gelöscht'); } };
  return <div className="space-y-7"><PageHeading eyebrow="Deine Stimme" title="Anschreiben" description="Weniger Floskeln. Mehr von dir. Verwalte deine Entwürfe und finde die richtigen Worte." action={<Button onClick={() => setShowModal(true)} testId="button-new-letter"><Plus size={17} />Neuer Entwurf</Button>} /><div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{state.letters.map((letter, index) => <Card key={letter.id} className={`group flex min-h-[250px] flex-col p-6 transition hover:-translate-y-1 ${index === 0 ? 'border-[hsl(var(--primary)/.45)]' : ''}`}><div className="flex items-start justify-between"><div className="flex h-11 w-11 items-center justify-center rounded-xl bg-[hsl(12_73%_57%/.12)] text-[hsl(var(--primary))]"><PenLine size={19} /></div><Badge tone={letter.status === 'Bereit zum Senden' ? 'teal' : letter.status === 'Archiviert' ? 'neutral' : 'yellow'}>{letter.status}</Badge></div><div className="mt-7 font-display text-xl font-semibold leading-tight">{letter.title}</div><div className="mt-2 text-sm text-[hsl(var(--muted-foreground))]">{letter.company}</div><div className="mt-auto flex items-end justify-between border-t border-[hsl(var(--border))] pt-5"><div><div className="font-mono-app text-[10px] text-[hsl(var(--muted-foreground))]">Zuletzt bearbeitet</div><div className="mt-1 text-xs font-semibold">{letter.updatedAt}</div></div>{letter.score > 0 && <div className="text-right"><div className="font-mono-app text-[10px] text-[hsl(var(--muted-foreground))]">Match</div><div className="mt-1 font-display text-xl font-semibold text-[hsl(171_45%_35%)]">{letter.score}</div></div>}</div><div className="mt-4 flex gap-2 opacity-100 transition md:opacity-0 md:group-hover:opacity-100"><Button variant="secondary" onClick={() => setEditing(letter)} className="flex-1 py-2 text-xs" testId={`button-edit-letter-${letter.id}`}><Pencil size={14} />Öffnen</Button><IconButton label="Entwurf löschen" onClick={() => remove(letter.id)} className="h-9 w-9 border border-[hsl(var(--border))] text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--destructive))]"><Trash2 size={15} /></IconButton></div></Card>)}</div><Card className="grid items-center gap-5 p-6 sm:grid-cols-[1fr_auto] sm:p-7"><div><div className="mb-2 flex items-center gap-2 font-mono-app text-[10px] uppercase tracking-[.16em] text-[hsl(var(--primary))]"><Sparkles size={14} /> Schreibimpuls</div><h2 className="font-display text-2xl font-semibold">Was macht deine Arbeit anders?</h2><p className="mt-2 text-sm text-[hsl(var(--muted-foreground))]">Ein guter Anfang für ein Anschreiben, das im Gedächtnis bleibt.</p></div><Button variant="secondary" onClick={() => notify('Schreibimpuls kopiert')} testId="button-use-prompt">Impuls verwenden <ArrowUpRight size={15} /></Button></Card>{showModal && <Modal title="Neues Anschreiben" onClose={() => setShowModal(false)}><div className="space-y-4"><p className="text-sm leading-6 text-[hsl(var(--muted-foreground))]">Starte mit einem leeren Entwurf. Du kannst Titel und Unternehmen direkt anpassen.</p><Button onClick={add} className="w-full" testId="button-start-letter">Entwurf starten <ArrowUpRight size={16} /></Button></div></Modal>}{editing && <LetterEditor letter={editing} onClose={() => setEditing(null)} onSave={(next) => { setState(s => ({ ...s, letters: s.letters.map(l => l.id === next.id ? next : l) })); setEditing(null); notify('Anschreiben gespeichert'); }} />}</div>;
}

function LetterEditor({ letter, onClose, onSave }: { letter: Letter; onClose: () => void; onSave: (letter: Letter) => void }) {
  const [title, setTitle] = useState(letter.title); const [company, setCompany] = useState(letter.company); const [body, setBody] = useState('Ich mag Produkte, die Menschen nicht erklären müssen. Bei Morgen Studio sehe ich die Chance, komplexe Aufgaben klar und menschlich zu machen – genau dort liegt meine Stärke.');
  return <Modal title="Anschreiben bearbeiten" onClose={onClose}><div className="space-y-4"><Field label="Titel" value={title} onChange={setTitle} /><Field label="Unternehmen" value={company} onChange={setCompany} /><label className="block text-xs font-semibold">Text<textarea data-testid="textarea-letter" value={body} onChange={e => setBody(e.target.value)} rows={7} className="mt-2 w-full resize-none rounded-xl border border-[hsl(var(--border))] bg-[hsl(var(--background))] p-3 text-sm leading-6 outline-none focus:border-[hsl(var(--primary))]" /></label><div className="flex justify-end gap-2 pt-3"><Button variant="ghost" onClick={onClose}>Abbrechen</Button><Button onClick={() => onSave({ ...letter, title, company, updatedAt: 'Gerade eben', score: Math.max(letter.score, Math.min(98, Math.round(body.length / 2.2))), status: 'Bereit zum Senden' })} testId="button-save-letter"><Save size={16} />Speichern</Button></div></div></Modal>;
}

function InterviewPage({ state, setState, notify }: { state: LocalState; setState: React.Dispatch<React.SetStateAction<LocalState>>; notify: (message: string) => void }) {
  const [active, setActive] = useState(state.questions[0]?.id ?? 31); const question = state.questions.find(q => q.id === active) ?? state.questions[0]; const [answer, setAnswer] = useState(question?.answer ?? '');
  useEffect(() => setAnswer(question?.answer ?? ''), [question]);
  const saveAnswer = () => { if (!question) return; setState(s => ({ ...s, questions: s.questions.map(q => q.id === question.id ? { ...q, answer, feedback: answer.length > 80 ? 'Guter roter Faden. Ergänze noch eine konkrete Zahl und deinen persönlichen Beitrag.' : 'Deine Antwort ist ein guter Anfang. Erzähle noch etwas konkreter von deiner Rolle.' } : q) })); notify('Antwort gespeichert und Feedback erstellt'); };
  const done = state.questions.filter(q => q.answer).length;
  return <div className="space-y-7"><PageHeading eyebrow="Vorbereitung" title="Interview" description="Übe in deinem Tempo. Klare Gedanken sind die beste Vorbereitung." action={<Badge tone="teal">{done} von {state.questions.length} beantwortet</Badge>} /><div className="grid gap-5 lg:grid-cols-[.72fr_1.28fr]"><Card className="p-3 sm:p-4"><div className="p-3"><div className="mb-1 font-mono-app text-[10px] uppercase tracking-[.16em] text-[hsl(var(--muted-foreground))]">Fragenkatalog</div><div className="text-sm text-[hsl(var(--muted-foreground))]">Nächster Termin: morgen, 10:30 Uhr</div></div><div className="mt-3 space-y-1">{state.questions.map((q, i) => <button type="button" key={q.id} data-testid={`button-interview-question-${q.id}`} onClick={() => setActive(q.id)} className={`flex w-full items-start gap-3 rounded-xl p-3 text-left transition ${active === q.id ? 'bg-[hsl(var(--secondary))]' : 'hover:bg-[hsl(var(--background))]'}`}><span className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full font-mono-app text-[10px] ${q.answer ? 'bg-[hsl(171_45%_42%)] text-white' : active === q.id ? 'bg-[hsl(var(--primary))] text-white' : 'bg-[hsl(var(--muted))] text-[hsl(var(--muted-foreground))]'}`}>{q.answer ? <Check size={13} /> : `0${i + 1}`}</span><span className="text-xs font-semibold leading-5">{q.category}<span className="mt-0.5 block font-normal text-[hsl(var(--muted-foreground))]">{q.question.slice(0, 45)} …</span></span></button>)}</div></Card><Card className="p-6 sm:p-8">{question ? <><div className="mb-3 flex items-center gap-2"><Badge tone="coral">{question.category}</Badge><span className="font-mono-app text-[10px] text-[hsl(var(--muted-foreground))]">Frage {state.questions.findIndex(q => q.id === question.id) + 1} / {state.questions.length}</span></div><h2 className="max-w-2xl font-display text-3xl font-semibold leading-tight">{question.question}</h2><label className="mt-8 block text-xs font-semibold text-[hsl(var(--muted-foreground))]">Deine Antwort<textarea data-testid="textarea-interview-answer" value={answer} onChange={e => setAnswer(e.target.value)} placeholder="Schreib frei heraus. Perfekte Formulierungen kommen später …" rows={9} className="mt-2 w-full resize-none rounded-xl border border-[hsl(var(--border))] bg-[hsl(var(--background))] p-4 text-sm leading-6 outline-none transition focus:border-[hsl(var(--primary))]" /></label><div className="mt-4 flex flex-wrap items-center justify-between gap-3"><span className="font-mono-app text-[10px] text-[hsl(var(--muted-foreground))]">{answer.length} Zeichen</span><Button onClick={saveAnswer} testId="button-save-interview"><Save size={16} />Antwort speichern</Button></div>{question.feedback && <div className="mt-7 flex gap-3 rounded-xl bg-[hsl(var(--accent)/.18)] p-4"><Lightbulb size={18} className="mt-0.5 shrink-0 text-[hsl(37_70%_31%)]" /><div><div className="text-sm font-semibold">Dein Feedback</div><p className="mt-1 text-xs leading-5 text-[hsl(37_60%_28%)]">{question.feedback}</p></div></div>}</> : <EmptyState title="Noch keine Fragen" text="Lege Fragen an, um deine Vorbereitung zu starten." />}</Card></div><div className="flex items-center gap-2 text-xs text-[hsl(var(--muted-foreground))]"><CircleAlert size={15} />Tipp: Sprich deine Antwort einmal laut aus. So merkst du schnell, wo noch ein Gedanke fehlt.</div></div>;
}

function NotificationsPage({ state, setState, notify }: { state: LocalState; setState: React.Dispatch<React.SetStateAction<LocalState>>; notify: (message: string) => void }) {
  return <div className="space-y-7"><PageHeading eyebrow="Auf dem Laufenden" title="Benachrichtigungen" description="Die wichtigen Dinge – nicht jede Kleinigkeit." action={<Button variant="ghost" onClick={() => { setState(s => ({ ...s, notifications: s.notifications.map(n => ({ ...n, read: true })) })); notify('Alle Benachrichtigungen gelesen'); }} testId="button-mark-notifications-read"><Check size={16} />Alle gelesen</Button>} /><div className="grid gap-5 lg:grid-cols-[1.2fr_.8fr]"><Card className="overflow-hidden"><div className="border-b border-[hsl(var(--border))] px-6 py-5"><div className="font-display text-xl font-semibold">Dein Posteingang</div></div><div className="divide-y divide-[hsl(var(--border))]">{state.notifications.map(n => <button type="button" key={n.id} data-testid={`notification-${n.id}`} onClick={() => { setState(s => ({ ...s, notifications: s.notifications.map(item => item.id === n.id ? { ...item, read: true } : item) })); notify('Benachrichtigung geöffnet'); }} className={`flex w-full gap-4 px-6 py-5 text-left transition hover:bg-[hsl(var(--background))] ${!n.read ? 'bg-[hsl(12_73%_57%/.045)]' : ''}`}><div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${n.type === 'important' ? 'bg-[hsl(12_73%_57%/.13)] text-[hsl(var(--primary))]' : n.type === 'job' ? 'bg-[hsl(var(--secondary))] text-[hsl(174_35%_26%)]' : 'bg-[hsl(var(--accent)/.25)] text-[hsl(37_70%_31%)]'}`}>{n.type === 'important' ? <CalendarDays size={17} /> : n.type === 'job' ? <BriefcaseBusiness size={17} /> : <BarChart3 size={17} />}</div><div className="min-w-0 flex-1"><div className="flex items-center gap-2"><span className="text-sm font-semibold">{n.title}</span>{!n.read && <span className="h-1.5 w-1.5 rounded-full bg-[hsl(var(--primary))]" />}</div><p className="mt-1 text-xs leading-5 text-[hsl(var(--muted-foreground))]">{n.text}</p><div className="mt-2 font-mono-app text-[10px] text-[hsl(var(--muted-foreground))]">{n.time}</div></div><ChevronRight size={16} className="mt-1 text-[hsl(var(--muted-foreground))]" /></button>)}</div></Card><Card className="p-6 sm:p-7"><div className="mb-7 flex items-start gap-4"><div className="flex h-11 w-11 items-center justify-center rounded-xl bg-[hsl(var(--secondary))] text-[hsl(var(--secondary-foreground))]"><Mail size={19} /></div><div><h2 className="font-display text-2xl font-semibold">E-Mail-Erkennung</h2><p className="mt-1 text-xs leading-5 text-[hsl(var(--muted-foreground))]">Erhalte Hinweise, wenn eine Antwort zu deinen Bewerbungen eintrifft.</p></div></div><div className="rounded-xl border border-dashed border-[hsl(var(--border))] p-5 text-center"><Inbox size={22} className="mx-auto text-[hsl(var(--muted-foreground))]" /><div className="mt-3 text-sm font-semibold">Noch nicht verbunden</div><p className="mx-auto mt-1 max-w-xs text-xs leading-5 text-[hsl(var(--muted-foreground))]">In dieser Demo kannst du die Erkennung simulieren.</p><Button variant="secondary" onClick={() => notify('Demo-E-Mail erkannt: Einladung zum Gespräch bei Morgen Studio')} className="mt-5" testId="button-simulate-email"><Mail size={15} />E-Mail simulieren</Button></div></Card></div></div>;
}

function SettingsPage({ state, setState, notify }: { state: LocalState; setState: React.Dispatch<React.SetStateAction<LocalState>>; notify: (message: string) => void }) {
  const [name, setName] = useState(state.resume.name); const [email, setEmail] = useState(state.resume.email); const [weekly, setWeekly] = useState(true); const [reminders, setReminders] = useState(true);
  const save = () => { setState(s => ({ ...s, resume: { ...s.resume, name, email } })); notify('Einstellungen gespeichert'); };
  const reset = () => { if (window.confirm('Alle lokalen Demo-Daten zurücksetzen?')) { setState(initialState); notify('Demo-Daten zurückgesetzt'); } };
  return <div className="space-y-7"><PageHeading eyebrow="Dein Raum" title="Einstellungen" description="Passe deinen Bewerbungsraum so an, dass er dich unterstützt – nicht beschäftigt." /><div className="grid gap-5 lg:grid-cols-[1.15fr_.85fr]"><Card className="p-6 sm:p-8"><div className="mb-7"><div className="mb-1 font-mono-app text-[10px] uppercase tracking-[.16em] text-[hsl(var(--muted-foreground))]">Profil</div><h2 className="font-display text-2xl font-semibold">So bist du sichtbar</h2></div><div className="grid gap-4 sm:grid-cols-2"><Field label="Name" value={name} onChange={setName} /><Field label="E-Mail-Adresse" value={email} onChange={setEmail} /></div><div className="mt-7 flex justify-end"><Button onClick={save} testId="button-save-settings"><Save size={16} />Speichern</Button></div></Card><Card className="p-6 sm:p-8"><div className="mb-7"><div className="mb-1 font-mono-app text-[10px] uppercase tracking-[.16em] text-[hsl(var(--muted-foreground))]">Begleitung</div><h2 className="font-display text-2xl font-semibold">Benachrichtigungen</h2></div><div className="space-y-1"><Toggle label="Wöchentlicher Fokus" text="Montags mit einem klaren Plan starten" checked={weekly} onChange={() => setWeekly(!weekly)} testId="toggle-weekly" /><Toggle label="Erinnerungen" text="Wenn ein nächster Schritt fällig wird" checked={reminders} onChange={() => setReminders(!reminders)} testId="toggle-reminders" /></div></Card><Card className="p-6 sm:p-8 lg:col-span-2"><div className="mb-7"><div className="mb-1 font-mono-app text-[10px] uppercase tracking-[.16em] text-[hsl(var(--muted-foreground))]">Lokaler Speicher</div><h2 className="font-display text-2xl font-semibold">Deine Daten bleiben bei dir</h2><p className="mt-2 max-w-xl text-sm leading-6 text-[hsl(var(--muted-foreground))]">Diese Demo speichert alle Änderungen ausschließlich in deinem Browser. Du kannst jederzeit eine Kopie exportieren oder von vorne beginnen.</p></div><div className="flex flex-wrap gap-3"><Button variant="secondary" onClick={() => { const blob = new Blob([JSON.stringify(state, null, 2)], { type: 'application/json' }); const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = 'naechster-schritt-daten.json'; a.click(); URL.revokeObjectURL(url); notify('Daten exportiert'); }} testId="button-export-data"><Download size={16} />Daten exportieren</Button><Button variant="danger" onClick={reset} testId="button-reset-data"><Database size={16} />Demo-Daten zurücksetzen</Button></div></Card></div></div>;
}

function Toggle({ label, text, checked, onChange, testId }: { label: string; text: string; checked: boolean; onChange: () => void; testId: string }) { return <button type="button" data-testid={testId} onClick={onChange} className="flex w-full items-center justify-between rounded-xl p-3 text-left transition hover:bg-[hsl(var(--background))]"><div><div className="text-sm font-semibold">{label}</div><div className="mt-1 text-xs text-[hsl(var(--muted-foreground))]">{text}</div></div><span className={`relative h-6 w-11 rounded-full transition ${checked ? 'bg-[hsl(var(--primary))]' : 'bg-[hsl(var(--muted))]'}`}><span className={`absolute top-1 h-4 w-4 rounded-full bg-[hsl(var(--card))] shadow-sm transition-transform ${checked ? 'translate-x-6' : 'translate-x-1'}`} /></span></button>; }

function Field({ label, value, onChange, placeholder = '', required = false }: { label: string; value: string; onChange: (value: string) => void; placeholder?: string; required?: boolean }) { return <label className="block text-xs font-semibold">{label}{required && <span className="ml-1 text-[hsl(var(--primary))]">*</span>}<input required={required} data-testid={`input-${label.toLowerCase().replaceAll(' ', '-')}`} value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder} className="mt-2 h-11 w-full rounded-xl border border-[hsl(var(--border))] bg-[hsl(var(--background))] px-3 text-sm font-normal outline-none transition placeholder:text-[hsl(var(--muted-foreground)/.7)] focus:border-[hsl(var(--primary))] focus:ring-2 focus:ring-[hsl(var(--primary)/.12)]" /></label>; }
function SelectField({ label, value, onChange, options }: { label: string; value: string; onChange: (value: string) => void; options: string[] }) { return <label className="block text-xs font-semibold">{label}<select data-testid={`select-${label.toLowerCase()}`} value={value} onChange={e => onChange(e.target.value)} className="mt-2 h-11 w-full rounded-xl border border-[hsl(var(--border))] bg-[hsl(var(--background))] px-3 text-sm font-normal outline-none focus:border-[hsl(var(--primary))]">{options.map(o => <option key={o}>{o}</option>)}</select></label>; }
function TabButton({ active, onClick, label, testId }: { active: boolean; onClick: () => void; label: string; testId: string }) { return <button type="button" data-testid={testId} onClick={onClick} className={`border-b-2 px-4 pb-3 text-sm font-semibold transition ${active ? 'border-[hsl(var(--primary))] text-[hsl(var(--primary))]' : 'border-transparent text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--foreground))]'}`}>{label}</button>; }
function EmptyState({ icon, title, text, action }: { icon?: ReactNode; title: string; text: string; action?: ReactNode }) { return <div className="flex flex-col items-center justify-center px-6 py-16 text-center"><div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-[hsl(var(--secondary))] text-[hsl(var(--secondary-foreground))]">{icon ?? <Inbox size={22} />}</div><h3 className="mt-4 font-display text-xl font-semibold">{title}</h3><p className="mt-2 max-w-sm text-sm leading-6 text-[hsl(var(--muted-foreground))]">{text}</p>{action && <div className="mt-5">{action}</div>}</div>; }
function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) { return <div className="fixed inset-0 z-50 flex items-end justify-center bg-[hsl(217_32%_18%/.45)] p-0 backdrop-blur-sm sm:items-center sm:p-5"><div role="dialog" aria-modal="true" className="max-h-[92dvh] w-full max-w-lg overflow-y-auto rounded-t-3xl border border-[hsl(var(--border))] bg-[hsl(var(--card))] p-6 shadow-2xl sm:rounded-3xl sm:p-8"><div className="mb-7 flex items-center justify-between"><h2 className="font-display text-2xl font-semibold">{title}</h2><IconButton label="Fenster schließen" onClick={onClose} className="h-9 w-9"><X size={18} /></IconButton></div>{children}</div></div>; }

function Router() {
  const { state, setState, toast, notify } = useLocalState();
  return <Shell><Switch><Route path="/" component={() => <Dashboard state={state} notify={notify} />} /><Route path="/bewerbungen" component={() => <ApplicationsPage state={state} setState={setState} notify={notify} />} /><Route path="/stellen" component={() => <JobsPage state={state} setState={setState} notify={notify} />} /><Route path="/lebenslauf" component={() => <ResumePage state={state} setState={setState} notify={notify} />} /><Route path="/anschreiben" component={() => <LettersPage state={state} setState={setState} notify={notify} />} /><Route path="/interview" component={() => <InterviewPage state={state} setState={setState} notify={notify} />} /><Route path="/benachrichtigungen" component={() => <NotificationsPage state={state} setState={setState} notify={notify} />} /><Route path="/einstellungen" component={() => <SettingsPage state={state} setState={setState} notify={notify} />} /><Route component={NotFound} /></Switch><Toast message={toast} /></Shell>;
}
function RoutedErrorBoundary({ children }: { children: ReactNode }) { const [location] = useLocation(); return <ErrorBoundary resetKey={location}>{children}</ErrorBoundary>; }
function App() { return <QueryClientProvider client={queryClient}><TooltipProvider><WouterRouter base={import.meta.env.BASE_URL.replace(/\/$/, '')}><RoutedErrorBoundary><Router /></RoutedErrorBoundary></WouterRouter><Toaster /></TooltipProvider></QueryClientProvider>; }
export default App;
