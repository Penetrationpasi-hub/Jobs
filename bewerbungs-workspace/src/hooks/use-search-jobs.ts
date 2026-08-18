import { useQuery, type UseQueryOptions } from '@tanstack/react-query';

export type ExternalJob = {
  id: string;
  title: string;
  company: string;
  location: string;
  url: string;
  source: string;
  salary?: string | null;
  posted: string;
  description?: string | null;
};

type SearchParams = { q: string; l?: string; radius?: number };

const ADZUNA_APP_ID = import.meta.env.VITE_ADZUNA_APP_ID as string | undefined;
const ADZUNA_APP_KEY = import.meta.env.VITE_ADZUNA_APP_KEY as string | undefined;

type AdzunaResult = {
  id: string;
  title: string;
  company?: { display_name?: string };
  location?: { display_name?: string };
  redirect_url?: string;
  salary_min?: number;
  salary_max?: number;
  created?: string;
  description?: string;
};

async function fetchAdzuna(params: SearchParams): Promise<ExternalJob[]> {
  if (!ADZUNA_APP_ID || !ADZUNA_APP_KEY) return [];
  const url = new URL('https://api.adzuna.com/v1/api/jobs/de/search/1');
  url.searchParams.set('app_id', ADZUNA_APP_ID);
  url.searchParams.set('app_key', ADZUNA_APP_KEY);
  url.searchParams.set('what', params.q);
  url.searchParams.set('results_per_page', '15');
  url.searchParams.set('content-type', 'application/json');
  if (params.l) {
    url.searchParams.set('where', params.l);
    if (params.radius) url.searchParams.set('distance', String(params.radius));
  }
  const res = await fetch(url.toString());
  if (!res.ok) throw new Error(`Adzuna HTTP ${res.status}`);
  const data = (await res.json()) as { results?: AdzunaResult[] };
  return (data.results ?? []).map((r) => {
    const hasSalary = Boolean(r.salary_min || r.salary_max);
    const min = r.salary_min ? Math.round(r.salary_min) : null;
    const max = r.salary_max ? Math.round(r.salary_max) : null;
    return {
      id: `adzuna-${r.id}`,
      title: r.title,
      company: r.company?.display_name || '',
      location: r.location?.display_name || '',
      url: r.redirect_url || 'https://www.adzuna.de/',
      source: 'Adzuna',
      salary: hasSalary
        ? `${(min ?? max)!.toLocaleString('de-DE')}${max && min && max !== min ? ` – ${max.toLocaleString('de-DE')}` : ''} €`
        : null,
      posted: r.created ? new Date(r.created).toLocaleDateString('de-DE') : '',
      description: r.description ?? null,
    };
  });
}

type ArbeitnowResult = {
  slug: string;
  title: string;
  company_name: string;
  location: string;
  url: string;
  created_at: number;
  description?: string;
};

async function fetchArbeitnow(params: SearchParams): Promise<ExternalJob[]> {
  const res = await fetch('https://www.arbeitnow.com/api/job-board-api');
  if (!res.ok) throw new Error(`Arbeitnow HTTP ${res.status}`);
  const data = (await res.json()) as { data?: ArbeitnowResult[] };
  const q = params.q.trim().toLowerCase();
  const loc = params.l?.trim().toLowerCase();
  return (data.data ?? [])
    .filter(
      (j) =>
        (j.title.toLowerCase().includes(q) || j.company_name.toLowerCase().includes(q)) &&
        (!loc || j.location.toLowerCase().includes(loc)),
    )
    .slice(0, 15)
    .map((j) => ({
      id: `arbeitnow-${j.slug}`,
      title: j.title,
      company: j.company_name,
      location: j.location,
      url: j.url,
      source: 'Arbeitnow',
      salary: null,
      posted: j.created_at ? new Date(j.created_at * 1000).toLocaleDateString('de-DE') : '',
      description: j.description ?? null,
    }));
}

// Ersetzt die fehlende `@workspace/api-client-react`-Anbindung: statt über ein
// eigenes Backend werden Adzuna und Arbeitnow direkt aus dem Browser abgefragt.
// Adzuna app_id/app_key liegen dadurch im Client-Bundle (siehe README-Hinweis).
export function useSearchJobs(
  params: SearchParams,
  options?: { query?: Partial<UseQueryOptions<ExternalJob[]>> },
) {
  return useQuery<ExternalJob[]>({
    queryKey: ['searchJobs', params.q, params.l, params.radius],
    queryFn: async () => {
      const [adzuna, arbeitnow] = await Promise.allSettled([fetchAdzuna(params), fetchArbeitnow(params)]);
      return [
        ...(adzuna.status === 'fulfilled' ? adzuna.value : []),
        ...(arbeitnow.status === 'fulfilled' ? arbeitnow.value : []),
      ];
    },
    enabled: params.q.trim().length >= 2,
    ...options?.query,
  });
}
