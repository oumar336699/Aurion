export type SupabaseConfig = {
  url: string;
  anonKey: string;
};

export type PricePoint = {
  timestamp: string;
  prix_usd: number;
  source: string;
};

export type SignalRow = {
  timestamp: string;
  signal: 'ACHAT' | 'VENTE' | 'ATTENTE';
  prix_au_moment: number;
  moyenne_courte: number | null;
  moyenne_longue: number | null;
  rsi: number | null;
  confiance: number | null;
};

export type DashboardData = {
  prices: PricePoint[];
  signals: SignalRow[];
  pricesError: string | null;
  signalsError: string | null;
};

const REQUEST_TIMEOUT_MS = 12000;

function normalizeBaseUrl(value: string) {
  const url = value.trim().replace(/\/+$/, '');
  const parsed = new URL(url);
  if (parsed.protocol !== 'https:' && parsed.hostname !== 'localhost') {
    throw new Error('L’URL Supabase doit utiliser HTTPS.');
  }
  return url;
}

async function getRows<T>(config: SupabaseConfig, table: string, query: string): Promise<T[]> {
  const baseUrl = normalizeBaseUrl(config.url);
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  try {
    const response = await fetch(`${baseUrl}/rest/v1/${table}?${query}`, {
      method: 'GET',
      headers: {
        apikey: config.anonKey.trim(),
        Authorization: `Bearer ${config.anonKey.trim()}`,
        Accept: 'application/json',
      },
      signal: controller.signal,
    });
    if (!response.ok) {
      const details = await response.json().catch(() => null);
      const message = typeof details?.message === 'string' ? details.message : response.statusText;
      throw new Error(`Supabase ${table} (${response.status}): ${message || 'requête refusée'}`);
    }
    const rows: unknown = await response.json();
    if (!Array.isArray(rows)) throw new Error(`Réponse Supabase ${table} invalide.`);
    return rows as T[];
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') {
      throw new Error(`Délai dépassé pendant le chargement de ${table}.`);
    }
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}

function messageFor(error: unknown) {
  return error instanceof Error ? error.message : 'Erreur de connexion Supabase.';
}

export async function loadDashboard(config: SupabaseConfig): Promise<DashboardData> {
  const [pricesResult, signalsResult] = await Promise.allSettled([
    getRows<PricePoint>(config, 'prix', 'select=timestamp,prix_usd,source&order=timestamp.desc&limit=168'),
    getRows<SignalRow>(
      config,
      'signaux',
      'select=timestamp,signal,prix_au_moment,moyenne_courte,moyenne_longue,rsi,confiance&order=timestamp.desc&limit=40',
    ),
  ]);

  return {
    prices: pricesResult.status === 'fulfilled'
      ? pricesResult.value.sort((left, right) => Date.parse(left.timestamp) - Date.parse(right.timestamp))
      : [],
    signals: signalsResult.status === 'fulfilled'
      ? signalsResult.value.sort((left, right) => Date.parse(right.timestamp) - Date.parse(left.timestamp))
      : [],
    pricesError: pricesResult.status === 'rejected' ? messageFor(pricesResult.reason) : null,
    signalsError: signalsResult.status === 'rejected' ? messageFor(signalsResult.reason) : null,
  };
}
