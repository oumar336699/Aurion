import { MaterialCommunityIcons } from '@expo/vector-icons';
import { useEffect, useState } from 'react';
import { Alert, StyleSheet, Text, TextInput, View } from 'react-native';

import { ActionButton, AppScreen, BrandHeader, InlineNotice } from '../../components/ui';
import { SupabaseConfig } from '../../lib/data';
import { useMarket } from '../../state/market';
import { C } from '../../theme';

export default function SettingsScreen() {
  const { config, saveConfig, clearConfig, refreshing, pricesError, signalsError, lastUpdated } = useMarket();
  const [url, setUrl] = useState(config?.url ?? '');
  const [anonKey, setAnonKey] = useState(config?.anonKey ?? '');
  const [showKey, setShowKey] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setUrl(config?.url ?? '');
    setAnonKey(config?.anonKey ?? '');
  }, [config]);

  async function connect() {
    setError(null);
    setMessage(null);
    if (!url.trim() || !anonKey.trim()) {
      setError('Renseigne l’URL Supabase et la clé anon.');
      return;
    }
    try {
      const parsed = new URL(url.trim());
      if (parsed.protocol !== 'https:' && parsed.hostname !== 'localhost') {
        setError('L’URL Supabase doit commencer par https://.');
        return;
      }
      setSaving(true);
      await saveConfig({ url: url.trim(), anonKey: anonKey.trim() } satisfies SupabaseConfig);
      setMessage('Configuration enregistrée. Les tables accessibles apparaîtront dans Marché et Signaux.');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Impossible d’enregistrer la configuration.');
    } finally {
      setSaving(false);
    }
  }

  function disconnect() {
    Alert.alert('Effacer la configuration ?', 'La clé enregistrée sur cet appareil sera supprimée.', [
      { text: 'Annuler', style: 'cancel' },
      { text: 'Effacer', style: 'destructive', onPress: () => void clearConfig() },
    ]);
  }

  return (
    <AppScreen>
      <BrandHeader eyebrow="Connexion sécurisée" title="Réglages" />
      <View style={styles.statusRow}>
        <MaterialCommunityIcons name={config ? 'shield-check-outline' : 'shield-lock-outline'} size={20} color={config ? C.green : C.gold} />
        <View style={styles.statusCopy}>
          <Text style={styles.statusTitle}>{config ? 'Connexion configurée' : 'Connexion non configurée'}</Text>
          <Text style={styles.statusDetail}>{lastUpdated ? `Dernière lecture ${lastUpdated.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}` : 'Lecture seule via Supabase REST'}</Text>
        </View>
        {refreshing ? <MaterialCommunityIcons name="loading" size={18} color={C.gold} /> : null}
      </View>

      {(pricesError || signalsError) ? (
        <InlineNotice
          title="Vérifie les accès Supabase"
          message={[pricesError, signalsError].filter(Boolean).join(' · ')}
          tone="error"
          icon="database-alert-outline"
        />
      ) : null}
      {error ? <InlineNotice title="Configuration invalide" message={error} tone="error" /> : null}
      {message ? <InlineNotice title="Enregistré" message={message} icon="check-circle-outline" /> : null}

      <View style={styles.form}>
        <Text style={styles.fieldLabel}>URL du projet Supabase</Text>
        <TextInput
          value={url}
          onChangeText={setUrl}
          placeholder="https://votre-projet.supabase.co"
          placeholderTextColor={C.faint}
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="url"
          style={styles.input}
          accessibilityLabel="URL du projet Supabase"
        />
        <Text style={styles.fieldLabel}>Clé publique anon</Text>
        <View style={styles.keyInputWrap}>
          <TextInput
            value={anonKey}
            onChangeText={setAnonKey}
            placeholder="sb_publishable_… ou clé anon"
            placeholderTextColor={C.faint}
            autoCapitalize="none"
            autoCorrect={false}
            secureTextEntry={!showKey}
            style={[styles.input, styles.keyInput]}
            accessibilityLabel="Clé anon Supabase"
          />
          <Text onPress={() => setShowKey((visible) => !visible)} style={styles.reveal} accessibilityRole="button">
            {showKey ? 'Masquer' : 'Afficher'}
          </Text>
        </View>
        <ActionButton label={saving ? 'Connexion…' : 'Enregistrer et synchroniser'} icon="cloud-sync-outline" disabled={saving} onPress={() => void connect()} />
        {config ? <ActionButton label="Effacer cette configuration" icon="delete-outline" quiet onPress={disconnect} /> : null}
      </View>

      <View style={styles.security}>
        <Text style={styles.securityTitle}>Accès en lecture seule</Text>
        <Text style={styles.securityCopy}>Utilise uniquement la clé anon/public du projet. N’entre jamais DATABASE_URL ni une clé service_role. Active les politiques RLS pour autoriser SELECT sur prix et signaux; les tables d’ordres ne sont pas utilisées par l’app.</Text>
      </View>
    </AppScreen>
  );
}

const styles = StyleSheet.create({
  statusRow: { flexDirection: 'row', alignItems: 'center', gap: 12, borderBottomWidth: 1, borderTopWidth: 1, borderColor: C.border, paddingVertical: 15 },
  statusCopy: { flex: 1, gap: 3 },
  statusTitle: { color: C.text, fontWeight: '600', fontSize: 14 },
  statusDetail: { color: C.muted, fontSize: 11 },
  form: { gap: 11 },
  fieldLabel: { color: C.gold, fontSize: 11, fontWeight: '700', marginTop: 4 },
  input: { height: 50, borderWidth: 1, borderColor: C.border, borderRadius: 10, backgroundColor: C.surface, paddingHorizontal: 13, color: C.text, fontSize: 13 },
  keyInputWrap: { flexDirection: 'row', alignItems: 'center' },
  keyInput: { flex: 1, paddingRight: 76 },
  reveal: { position: 'absolute', right: 13, color: C.gold, fontSize: 11, fontWeight: '600', paddingVertical: 12 },
  security: { borderLeftWidth: 2, borderColor: C.gold, paddingLeft: 13, gap: 6, marginTop: 3 },
  securityTitle: { color: C.text, fontSize: 13, fontWeight: '600' },
  securityCopy: { color: C.muted, fontSize: 12, lineHeight: 18 },
});