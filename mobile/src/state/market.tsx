import AsyncStorage from '@react-native-async-storage/async-storage';
import { createContext, useContext, useEffect, useState } from 'react';

import { DashboardData, loadDashboard, SupabaseConfig } from '../lib/data';

const STORAGE_KEY = 'aurion.supabase.readonly.v1';

type MarketContextValue = DashboardData & {
  config: SupabaseConfig | null;
  ready: boolean;
  loading: boolean;
  refreshing: boolean;
  lastUpdated: Date | null;
  refresh: () => Promise<void>;
  saveConfig: (config: SupabaseConfig) => Promise<void>;
  clearConfig: () => Promise<void>;
};

const emptyData: DashboardData = {
  prices: [],
  signals: [],
  pricesError: null,
  signalsError: null,
};

const MarketContext = createContext<MarketContextValue | null>(null);

export function MarketProvider({ children }: { children: React.ReactNode }) {
  const [config, setConfig] = useState<SupabaseConfig | null>(null);
  const [data, setData] = useState<DashboardData>(emptyData);
  const [ready, setReady] = useState(false);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  async function refreshWith(target: SupabaseConfig | null) {
    if (!target) {
      setData(emptyData);
      setLoading(false);
      setRefreshing(false);
      return;
    }
    setRefreshing(true);
    setData((current) => ({ ...current, pricesError: null, signalsError: null }));
    try {
      const next = await loadDashboard(target);
      setData(next);
      setLastUpdated(new Date());
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Impossible de charger les données.';
      setData((current) => ({ ...current, pricesError: message }));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }

  useEffect(() => {
    let mounted = true;
    AsyncStorage.getItem(STORAGE_KEY)
      .then((stored) => {
        if (!mounted) return;
        if (!stored) {
          setLoading(false);
          setReady(true);
          return;
        }
        try {
          const parsed = JSON.parse(stored) as SupabaseConfig;
          if (!parsed.url || !parsed.anonKey) throw new Error('Configuration incomplète');
          setConfig(parsed);
          setReady(true);
          void refreshWith(parsed);
        } catch {
          void AsyncStorage.removeItem(STORAGE_KEY);
          setLoading(false);
          setReady(true);
        }
      })
      .catch(() => {
        if (mounted) {
          setLoading(false);
          setReady(true);
        }
      });
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    if (!config) return;
    const interval = setInterval(() => void refreshWith(config), 15 * 60 * 1000);
    return () => clearInterval(interval);
  }, [config]);

  async function refresh() {
    await refreshWith(config);
  }

  async function saveConfig(next: SupabaseConfig) {
    const normalized = { url: next.url.trim().replace(/\/+$/, ''), anonKey: next.anonKey.trim() };
    await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(normalized));
    setConfig(normalized);
    setLoading(true);
    await refreshWith(normalized);
  }

  async function clearConfig() {
    await AsyncStorage.removeItem(STORAGE_KEY);
    setConfig(null);
    setData(emptyData);
    setLastUpdated(null);
    setLoading(false);
  }

  return (
    <MarketContext.Provider
      value={{ ...data, config, ready, loading, refreshing, lastUpdated, refresh, saveConfig, clearConfig }}
    >
      {children}
    </MarketContext.Provider>
  );
}

export function useMarket() {
  const value = useContext(MarketContext);
  if (!value) throw new Error('useMarket doit être utilisé dans MarketProvider.');
  return value;
}
