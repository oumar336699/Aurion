import { MaterialCommunityIcons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { LinearGradient } from 'expo-linear-gradient';
import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { ActionButton, AppScreen, BrandHeader, IconButton, InlineNotice, Metric, PriceChart, SectionTitle, SignalBadge, formatMoney, formatTimestamp } from '../../components/ui';
import { useMarket } from '../../state/market';
import { C, PAGE_GUTTER } from '../../theme';

type Range = 24 | 72 | 168;

export default function MarketScreen() {
  const router = useRouter();
  const { prices, signals, pricesError, loading, refreshing, lastUpdated, refresh, config } = useMarket();
  const [range, setRange] = useState<Range>(168);
  const latest = prices.at(-1);
  const previous = prices.at(-2);
  const variation = latest && previous
    ? ((Number(latest.prix_usd) / Number(previous.prix_usd)) - 1) * 100
    : null;
  const chartPrices = prices.slice(-range);
  const lastSignal = signals[0];

  return (
    <AppScreen>
      <BrandHeader
        eyebrow="Cours tokenisé de l’or"
        title="PAX Gold"
        right={<IconButton icon={refreshing ? 'loading' : 'refresh'} label="Actualiser" onPress={() => void refresh()} />}
      />

      {pricesError ? (
        <InlineNotice title="Données indisponibles" message={pricesError} tone="error" icon="cloud-alert-outline" />
      ) : null}

      {!config ? (
        <View style={styles.emptySetup}>
          <MaterialCommunityIcons name="database-lock-outline" size={26} color={C.gold} />
          <Text style={styles.emptyTitle}>Connecte tes données</Text>
          <Text style={styles.emptyCopy}>Ajoute l’URL Supabase et la clé anon du projet dans Réglages. Aucun cours fictif n’est affiché.</Text>
          <ActionButton label="Configurer Supabase" icon="arrow-right" onPress={() => router.push('/settings')} />
        </View>
      ) : null}

      {config && loading && prices.length === 0 ? (
        <View style={styles.waiting}>
          <MaterialCommunityIcons name="chart-timeline-variant" size={26} color={C.gold} />
          <Text style={styles.emptyCopy}>Lecture des clôtures horaires…</Text>
        </View>
      ) : null}

      {config && latest ? (
        <>
          <LinearGradient colors={['#173754', '#0D2037', '#0A1A2C']} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={styles.pricePanel}>
            <View style={styles.pricePanelTop}>
              <Text style={styles.instrument}>PAXG / USDT</Text>
              <View style={styles.marketLive}><View style={styles.liveDot} /><Text style={styles.liveText}>CLÔTURE 1H</Text></View>
            </View>
            <Text style={styles.price}>{formatMoney(Number(latest.prix_usd), 2)} <Text style={styles.currency}>USDT</Text></Text>
            <View style={styles.priceFooter}>
              <View style={[styles.changePill, { backgroundColor: variation != null && variation < 0 ? '#DF8B811A' : '#75C7A11A' }]}>
                <MaterialCommunityIcons name={variation != null && variation < 0 ? 'arrow-bottom-right' : 'arrow-top-right'} size={15} color={variation != null && variation < 0 ? C.red : C.green} />
                <Text style={[styles.changeText, { color: variation != null && variation < 0 ? C.red : C.green }]}>
                  {variation == null ? '—' : `${variation >= 0 ? '+' : ''}${formatMoney(variation, 2)}%`}
                </Text>
              </View>
              <Text style={styles.priceTime}>{formatTimestamp(latest.timestamp)}</Text>
            </View>
          </LinearGradient>

          <View style={styles.chartSection}>
            <SectionTitle title="Historique" detail={`${chartPrices.length} clôtures`} />
            <View style={styles.chartBox}>
              {chartPrices.length > 1 ? <PriceChart prices={chartPrices} height={174} /> : (
                <View style={styles.chartEmpty}><Text style={styles.emptyCopy}>Historique insuffisant pour tracer la courbe.</Text></View>
              )}
              {chartPrices.length > 1 ? (
                <View style={styles.chartLabels}>
                  <Text style={styles.axisLabel}>{formatMoney(Math.min(...chartPrices.map((p) => Number(p.prix_usd))), 0)}</Text>
                  <Text style={styles.axisLabel}>{formatMoney(Math.max(...chartPrices.map((p) => Number(p.prix_usd))), 0)}</Text>
                </View>
              ) : null}
            </View>
            <View style={styles.rangeRow}>
              {([{ value: 24, label: '24H' }, { value: 72, label: '3J' }, { value: 168, label: '7J' }] as const).map((item) => (
                <Pressable key={item.value} onPress={() => setRange(item.value)} style={[styles.rangeButton, range === item.value && styles.rangeSelected]}>
                  <Text style={[styles.rangeText, range === item.value && styles.rangeTextSelected]}>{item.label}</Text>
                </Pressable>
              ))}
            </View>
          </View>

          <View style={styles.metricsRow}>
            <Metric label="Prix de clôture" value={`${formatMoney(Number(latest.prix_usd))}`} sub="USDT par PAXG" />
            <Metric label="Variation horaire" value={variation == null ? '—' : `${variation >= 0 ? '+' : ''}${formatMoney(variation)}%`} sub="vs clôture précédente" />
          </View>

          <View style={styles.signalSection}>
            <SectionTitle title="Signal récent" detail="Moteur Aurion" />
            {lastSignal ? (
              <View style={styles.signalSummary}>
                <View style={styles.signalSummaryTop}>
                  <SignalBadge signal={lastSignal.signal} />
                  <Text style={styles.priceTime}>{formatTimestamp(lastSignal.timestamp)}</Text>
                </View>
                <Text style={styles.signalPrice}>{formatMoney(Number(lastSignal.prix_au_moment))} USDT</Text>
                <Text style={styles.mutedCopy}>Confiance ML: {lastSignal.confiance == null ? 'non disponible' : `${formatMoney(Number(lastSignal.confiance) * 100, 1)}%`}</Text>
              </View>
            ) : <Text style={styles.emptyCopy}>Aucun signal enregistré.</Text>}
          </View>
        </>
      ) : null}

      <Text style={styles.syncLine}>{lastUpdated ? `Synchronisé ${formatTimestamp(lastUpdated.toISOString())}` : 'Actualisation automatique toutes les 15 minutes'}</Text>
    </AppScreen>
  );
}

const styles = StyleSheet.create({
  pricePanel: { minHeight: 178, borderRadius: 18, padding: 21, justifyContent: 'space-between', borderWidth: 1, borderColor: '#D8B76A33' },
  pricePanelTop: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  instrument: { color: C.muted, fontSize: 11, fontWeight: '700', letterSpacing: 1 },
  marketLive: { flexDirection: 'row', alignItems: 'center', gap: 7 },
  liveDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: C.green },
  liveText: { color: C.gold, fontSize: 9, fontWeight: '700', letterSpacing: 0.8 },
  price: { color: C.text, fontSize: 35, fontWeight: '600', fontVariant: ['tabular-nums'] },
  currency: { color: C.muted, fontSize: 13, fontWeight: '500' },
  priceFooter: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  changePill: { borderRadius: 99, paddingHorizontal: 9, paddingVertical: 5, flexDirection: 'row', alignItems: 'center', gap: 4 },
  changeText: { fontSize: 12, fontWeight: '700' },
  priceTime: { color: C.muted, fontSize: 11 },
  chartSection: { gap: 14 },
  chartBox: { gap: 5 },
  chartLabels: { flexDirection: 'row', justifyContent: 'space-between' },
  axisLabel: { color: C.faint, fontSize: 10 },
  chartEmpty: { height: 140, justifyContent: 'center', alignItems: 'center' },
  rangeRow: { flexDirection: 'row', gap: 8 },
  rangeButton: { minWidth: 58, height: 34, alignItems: 'center', justifyContent: 'center', borderRadius: 9, borderWidth: 1, borderColor: C.border },
  rangeSelected: { backgroundColor: C.gold, borderColor: C.gold },
  rangeText: { color: C.muted, fontSize: 11, fontWeight: '600' },
  rangeTextSelected: { color: C.background },
  metricsRow: { flexDirection: 'row', borderTopWidth: 1, borderBottomWidth: 1, borderColor: C.border },
  signalSection: { gap: 14 },
  signalSummary: { paddingVertical: 13, borderTopWidth: 1, borderColor: C.border, gap: 9 },
  signalSummaryTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  signalPrice: { color: C.text, fontSize: 19, fontWeight: '600' },
  mutedCopy: { color: C.muted, fontSize: 12 },
  emptySetup: { minHeight: 235, borderWidth: 1, borderColor: C.border, borderRadius: 16, backgroundColor: C.surface, padding: 22, gap: 14, justifyContent: 'center' },
  emptyTitle: { color: C.text, fontSize: 18, fontWeight: '600' },
  emptyCopy: { color: C.muted, fontSize: 13, lineHeight: 20 },
  waiting: { minHeight: 150, alignItems: 'center', justifyContent: 'center', gap: 14 },
  syncLine: { color: C.faint, fontSize: 10, textAlign: 'center', paddingTop: 3 },
});