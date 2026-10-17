import { MaterialCommunityIcons } from '@expo/vector-icons';
import { Tabs } from 'expo-router';

import { C } from '../../theme';

export default function TabLayout() {
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        sceneStyle: { backgroundColor: C.background },
        tabBarActiveTintColor: C.goldBright,
        tabBarInactiveTintColor: C.faint,
        tabBarStyle: {
          height: 66,
          paddingTop: 8,
          paddingBottom: 8,
          backgroundColor: C.background,
          borderTopColor: C.border,
        },
        tabBarLabelStyle: { fontSize: 10, fontWeight: '600' },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: 'Marché',
          tabBarIcon: ({ color, size }) => <MaterialCommunityIcons name="chart-areaspline" color={color} size={size} />,
        }}
      />
      <Tabs.Screen
        name="signals"
        options={{
          title: 'Signaux',
          tabBarIcon: ({ color, size }) => <MaterialCommunityIcons name="signal" color={color} size={size} />,
        }}
      />
      <Tabs.Screen
        name="settings"
        options={{
          title: 'Réglages',
          tabBarIcon: ({ color, size }) => <MaterialCommunityIcons name="tune-variant" color={color} size={size} />,
        }}
      />
    </Tabs>
  );
}