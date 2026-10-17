import { MaterialCommunityIcons } from '@expo/vector-icons';
import { useEffect, useRef } from 'react';
import {
  ActivityIndicator,
  Animated,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
  ViewStyle,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import Svg, { Defs, LinearGradient, Line, Path, Polygon, Stop } from 'react-native-svg';

import { PricePoint, SignalRow } from '../lib/data';
import { C, PAGE_GUTTER } from '../theme';

export function AppScreen({ children, scroll = true }: { children: React.ReactNode; scroll?: boolean }) {
  return (
    <SafeAreaView style={styles.safe} edges={['top', 'left', 'right']}>
      {scroll ? (
        <ScrollView contentContainerStyle={styles.page} showsVerticalScrollIndicator={false}>
          {children}
        </ScrollView>
      ) : children}
    </SafeAreaView>
  );
}

export function BrandMark({ size = 42 }: { size?: number }) {
  return (
    <View style={[styles.mark, { width: size, height: size, borderRadius: size * 0.28 }]}>
      <Svg width={size * 0.58} height={size * 0.58} viewBox="0 0 48 48">
        <Polygon points="15,7 34,7 43,39 5,39" fill={C.gold} />
        <Path d="M14 30h20M17 22h15M20 14h10" stroke={C.background} strokeWidth="2" opacity="0.65" />
      </Svg>
    </View>
  );
}

export function BrandHeader({
  eyebrow,
  title,
  right,
}: {
  eyebrow: string;
  title: string;
  right?: React.ReactNode;
}) {
  return (
    <View style={styles.header}>
      <View style={styles.headerTop}>
        <View style={styles.brandRow}>
          <BrandMark size={40} />
          <Text style={styles.brandName}>Aurion</Text>
        </View>
        {right}
      </View>
      <Text style={styles.eyebrow}>{eyebrow.toUpperCase()}</Text>
      <Text style={styles.pageTitle}>{title}</Text>
    </View>
  );
}

export function BrandLoader({ label = 'Chargement des données' }: { label?: string }) {
  const spin = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    const loop = Animated.loop(
      Animated.timing(spin, { toValue: 1, duration: 1800, useNativeDriver: true }),
    );
    loop.start();
    return () => loop.stop();
  }, [spin]);
  const rotation = spin.interpolate({ inputRange: [0, 1], outputRange: ['0deg', '360deg'] });

  return (
    <View style={styles.loader}>
      <View style={styles.loaderOrbit}>
        <Animated.View style={[styles.loaderArc, { transform: [{ rotate: rotation }] }]} />
        <BrandMark size={38} />
      </View>
      <Text style={styles.loaderLabel}>{label}</Text>
    </View>
  );
}

export function SectionTitle({ title, detail }: { title: string; detail?: string }) {
  return (
    <View style={styles.sectionTitle}>
      <Text style={styles.sectionHeading}>{title}</Text>
      {detail ? <Text style={styles.sectionDetail}>{detail}</Text> : null}
    </View>
  );
}

export function ActionButton({
  label,
  onPress,
  icon,
  disabled = false,
  quiet = false,
}: {
  label: string;
  onPress: () => void;
  icon: React.ComponentProps<typeof MaterialCommunityIcons>['name'];
  disabled?: boolean;
  quiet?: boolean;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      onPress={onPress}
      disabled={disabled}
      style={({ pressed }) => [
        styles.action,
        quiet ? styles.actionQuiet : styles.actionPrimary,
        disabled && styles.actionDisabled,
        pressed && !disabled && styles.pressed,
      ]}
    >
      <MaterialCommunityIcons name={icon} size={18} color={quiet ? C.gold : C.background} />
      <Text style={[styles.actionText, quiet && styles.actionTextQuiet]}>{label}</Text>
    </Pressable>
  );
}

export function InlineNotice({
  title,
  message,
  icon = 'information-outline',
  tone = 'normal',
  action,
}: {
  title: string;
  message: string;
  icon?: React.ComponentProps<typeof MaterialCommunityIcons>['name'];
  tone?: 'normal' | 'error';
  action?: React.ReactNode;
}) {
  return (
    <View style={[styles.notice, tone === 'error' && styles.noticeError]}>
      <MaterialCommunityIcons name={icon} size={20} color={tone === 'error' ? C.red : C.gold} />
      <View style={styles.noticeCopy}>
        <Text style={styles.noticeTitle}>{title}</Text>
        <Text style={styles.noticeMessage}>{message}</Text>
        {action}
      </View>
    </View>
  );
}

export function LoadingRows() {
  return (
    <View style={styles.loadingRows}>
      <ActivityIndicator color={C.gold} />
      <Text style={styles.sectionDetail}>Synchronisation Supabase…</Text>
    </View>
  );
}

export function Metric({ label, value, sub, style }: { label: string; value: string; sub?: string; style?: ViewStyle }) {
  return (
    <View style={[styles.metric, style]}>
      <Text style={styles.metricLabel}>{label}</Text>
      <Text style={styles.metricValue} numberOfLines={1} adjustsFontSizeToFit>{value}</Text>
      {sub ? <Text style={styles.metricSub}>{sub}</Text> : null}
    </View>
  );
}

export function SignalBadge({ signal }: { signal: SignalRow['signal'] }) {
  const isBuy = signal === 'ACHAT';
  const isSell = signal === 'VENTE';
  const tint = isBuy ? C.green : isSell ? C.red : C.muted;
  return (
    <View style={[styles.signalBadge, { borderColor: `${tint}55`, backgroundColor: `${tint}12` }]}>
      <View style={[styles.signalDot, { backgroundColor: tint }]} />
      <Text style={[styles.signalBadgeText, { color: tint }]}>{signal}</Text>
    </View>
  );
}

export function PriceChart({ prices, height = 176 }: { prices: PricePoint[]; height?: number }) {
  const values = prices.map((item) => Number(item.prix_usd)).filter(Number.isFinite);
  if (values.length < 2) return null;
  const width = 340;
  const padX = 4;
  const padY = 12;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const points = values.map((value, index) => ({
    x: padX + (index / (values.length - 1)) * (width - padX * 2),
    y: height - padY - ((value - min) / span) * (height - padY * 2),
  }));
  const line = points.map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x} ${point.y}`).join(' ');
  const area = `${line} L ${width - padX} ${height} L ${padX} ${height} Z`;
  const last = points[points.length - 1];

  return (
    <Svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
      <Defs>
        <LinearGradient id="priceFill" x1="0" y1="0" x2="0" y2="1">
          <Stop offset="0" stopColor={C.gold} stopOpacity="0.22" />
          <Stop offset="1" stopColor={C.gold} stopOpacity="0" />
        </LinearGradient>
      </Defs>
      {[0.25, 0.55, 0.85].map((fraction) => (
        <Line
          key={fraction}
          x1="0"
          x2={width}
          y1={fraction * height}
          y2={fraction * height}
          stroke={C.border}
          strokeWidth="1"
          strokeDasharray="3 7"
        />
      ))}
      <Path d={area} fill="url(#priceFill)" />
      <Path d={line} fill="none" stroke={C.gold} strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" />
      <Path d={`M ${last.x - 5} ${last.y} a 5 5 0 1 0 10 0 a 5 5 0 1 0 -10 0`} fill={C.goldBright} />
    </Svg>
  );
}

export function formatMoney(value: number | null | undefined, digits = 2) {
  if (value == null || !Number.isFinite(Number(value))) return '—';
  return new Intl.NumberFormat('fr-FR', { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(Number(value));
}

export function formatTimestamp(value: string | null | undefined) {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return new Intl.DateTimeFormat('fr-FR', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }).format(date);
}

export function IconButton({
  icon,
  onPress,
  label,
}: {
  icon: React.ComponentProps<typeof MaterialCommunityIcons>['name'];
  onPress: () => void;
  label: string;
}) {
  return (
    <Pressable accessibilityRole="button" accessibilityLabel={label} onPress={onPress} style={styles.iconButton}>
      <MaterialCommunityIcons name={icon} size={19} color={C.gold} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: C.background },
  page: { paddingHorizontal: PAGE_GUTTER, paddingTop: 12, paddingBottom: 28, gap: 24 },
  header: { gap: 7 },
  headerTop: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  brandRow: { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 8 },
  mark: { alignItems: 'center', justifyContent: 'center', backgroundColor: C.surfaceRaised, borderWidth: 1, borderColor: '#D8B76A44' },
  brandName: { color: C.goldBright, fontFamily: 'serif', fontSize: 23, fontWeight: '600' },
  eyebrow: { color: C.gold, fontSize: 10, fontWeight: '700', letterSpacing: 1.3 },
  pageTitle: { color: C.text, fontSize: 30, fontWeight: '600', letterSpacing: 0 },
  loader: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 18, backgroundColor: C.background },
  loaderOrbit: { width: 78, height: 78, alignItems: 'center', justifyContent: 'center' },
  loaderArc: { position: 'absolute', width: 72, height: 72, borderRadius: 36, borderWidth: 2, borderColor: C.border, borderTopColor: C.gold, borderRightColor: C.gold },
  loaderLabel: { color: C.muted, fontSize: 13 },
  sectionTitle: { flexDirection: 'row', alignItems: 'baseline', justifyContent: 'space-between', gap: 10 },
  sectionHeading: { color: C.text, fontSize: 17, fontWeight: '600' },
  sectionDetail: { color: C.muted, fontSize: 12 },
  action: { minHeight: 48, borderRadius: 12, paddingHorizontal: 16, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 9 },
  actionPrimary: { backgroundColor: C.gold },
  actionQuiet: { borderWidth: 1, borderColor: C.border, backgroundColor: C.surface },
  actionDisabled: { opacity: 0.45 },
  pressed: { opacity: 0.8 },
  actionText: { color: C.background, fontSize: 14, fontWeight: '700' },
  actionTextQuiet: { color: C.goldBright },
  notice: { flexDirection: 'row', alignItems: 'flex-start', gap: 12, backgroundColor: C.surface, borderWidth: 1, borderColor: C.border, borderRadius: 12, padding: 15 },
  noticeError: { borderColor: '#DF8B8155' },
  noticeCopy: { flex: 1, gap: 5 },
  noticeTitle: { color: C.text, fontWeight: '600', fontSize: 14 },
  noticeMessage: { color: C.muted, fontSize: 13, lineHeight: 19 },
  loadingRows: { minHeight: 90, alignItems: 'center', justifyContent: 'center', gap: 10 },
  metric: { flex: 1, minWidth: 0, gap: 5, paddingVertical: 13, paddingHorizontal: 14, borderRightWidth: 1, borderColor: C.border },
  metricLabel: { color: C.muted, fontSize: 11 },
  metricValue: { color: C.text, fontSize: 17, fontWeight: '600', fontVariant: ['tabular-nums'] },
  metricSub: { color: C.faint, fontSize: 10 },
  signalBadge: { alignSelf: 'flex-start', borderWidth: 1, borderRadius: 99, paddingVertical: 5, paddingHorizontal: 9, flexDirection: 'row', gap: 6, alignItems: 'center' },
  signalDot: { width: 6, height: 6, borderRadius: 3 },
  signalBadgeText: { fontSize: 10, fontWeight: '700' },
  iconButton: { width: 42, height: 42, borderRadius: 12, alignItems: 'center', justifyContent: 'center', backgroundColor: C.surface, borderWidth: 1, borderColor: C.border },
});
