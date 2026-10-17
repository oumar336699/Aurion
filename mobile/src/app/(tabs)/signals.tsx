import { MaterialCommunityIcons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { StyleSheet, Text, View } from 'react-native';

import { ActionButton, AppScreen, BrandHeader, IconButton, InlineNotice, SignalBadge, formatMoney, formatTimestamp } from '../../components/ui';
import { useMarket } from '../../state/market';
import { C } from '../../theme';

export default function SignalsScreen() {
  const router = useRouter();
  const { signals, signalsError, config, refresh, refreshing } = useMarket();

  return (
    <AppScreen>
      <BrandHeader
        eyebrow="Moyennes mobiles · RSI"
        title="Signaux"
        right={<IconButton icon={refreshing ? 'loading' : 'refresh'} label="Actualiser" onPress={() => void refresh()} />}
      />
      <Text style={styles.disclaimer}>Signaux techniques historiques. Ils ne constituent pas une recommandation d’investissement.</Text>
      {signalsError ? <InlineNotice title="Signaux indisponibles" message={signalsError} tone="error" icon="database-alert-outline" /> : null}
      {!config ? (
        <View style={styles.empty}>
          <MaterialCommunityIcons name="database-lock-outline" size={26} color={C.gold} />
          <Text style={styles.emptyTitle}>Supabase n’est pas configuré</Text>
          <Text style={styles.emptyCopy}>Connecte la clé anon en lecture seule dans Réglages pour afficher les signaux réels.</Text>
          <ActionButton label="Ouvrir les réglages" icon="arrow-right" onPress={() => router.push('/settings')} />
        </View>
      ) : signals.length === 0 && !signalsError ? (
        <View style={styles.empty}>
          <MaterialCommunityIcons name="chart-bell-curve-cumulative" size={26} color={C.gold} />
          <Text style={styles.emptyTitle}>Aucun signal en base</Text>
          <Text style={styles.emptyCopy}>La table signaux ne contient pas encore de ligne disponible.</Text>
        </View>
      ) : (
        <View style={styles.list}>
          {signals.map((item, index) => (
            <View key={`${item.timestamp}-${index}`} style={styles.row}>
              <View style={styles.rowTop}>
                <SignalBadge signal={item.signal} />
                <Text style={styles.timestamp}>{formatTimestamp(item.timestamp)}</Text>
              </View>
              <Text style={styles.price}>{formatMoney(Number(item.prix_au_moment))} <Text style={styles.unit}>USDT</Text></Text>
              <View style={styles.details}>
                <View style={styles.detail}><Text style={styles.label}>RSI</Text><Text style={styles.value}>{item.rsi == null ? '—' : formatMoney(Number(item.rsi), 1)}</Text></View>
                <View style={styles.detail}><Text style={styles.label}>Moy. courte</Text><Text style={styles.value}>{formatMoney(item.moyenne_courte)}</Text></View>
                <View style={styles.detail}><Text style={styles.label}>Moy. longue</Text><Text style={styles.value}>{formatMoney(item.moyenne_longue)}</Text></View>
                <View style={styles.detail}><Text style={styles.label}>Confiance</Text><Text style={[styles.value, { color: item.confiance == null ? C.muted : C.goldBright }]}>{item.confiance == null ? '—' : `${formatMoney(Number(item.confiance) * 100, 1)}%`}</Text></View>
              </View>
            </View>
          ))}
        </View>
      )}
    </AppScreen>
  );
}

const styles = StyleSheet.create({
  disclaimer: { color: C.faint, fontSize: 12, lineHeight: 18, marginTop: -10 },
  list: { borderTopWidth: 1, borderColor: C.border },
  row: { paddingVertical: 17, gap: 10, borderBottomWidth: 1, borderColor: C.border },
  rowTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  timestamp: { color: C.muted, fontSize: 11 },
  price: { color: C.text, fontSize: 19, fontWeight: '600', fontVariant: ['tabular-nums'] },
  unit: { color: C.muted, fontSize: 11, fontWeight: '400' },
  details: { flexDirection: 'row', flexWrap: 'wrap', rowGap: 12 },
  detail: { width: '50%', gap: 4 },
  label: { color: C.faint, fontSize: 10 },
  value: { color: C.muted, fontSize: 12, fontVariant: ['tabular-nums'] },
  empty: { minHeight: 235, borderWidth: 1, borderColor: C.border, borderRadius: 16, backgroundColor: C.surface, padding: 22, gap: 14, justifyContent: 'center' },
  emptyTitle: { color: C.text, fontSize: 18, fontWeight: '600' },
  emptyCopy: { color: C.muted, fontSize: 13, lineHeight: 20 },
});