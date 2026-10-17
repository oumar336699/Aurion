import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';

import { MarketProvider } from '../state/market';
import { C } from '../theme';

export default function RootLayout() {
  return (
    <MarketProvider>
      <StatusBar style="light" backgroundColor={C.background} />
      <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: C.background } }} />
    </MarketProvider>
  );
}