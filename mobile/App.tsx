import { StatusBar } from 'expo-status-bar';
import { StyleSheet, Text, View } from 'react-native';

export default function App() {
  return (
    <View style={styles.container}>
      <Text style={styles.title}>Aurion</Text>
      <Text style={styles.caption}>Lance l’application depuis Expo Router.</Text>
      <StatusBar style="auto" />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#071426',
    alignItems: 'center',
    justifyContent: 'center',
  },
  title: { color: '#F1D99A', fontSize: 28, fontWeight: '700' },
  caption: { color: '#91A1B0', marginTop: 8 },
});
