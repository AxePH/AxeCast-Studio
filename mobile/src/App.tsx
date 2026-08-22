import React, { useState } from 'react';
import {
  StyleSheet,
  Text,
  View,
  TouchableOpacity,
  ScrollView,
  StatusBar,
  SafeAreaView,
  TextInput,
  Share,
} from 'react-native';

const APP_VERSION = 'v1.0.4';

export default function App() {
  const [activeMode, setActiveMode] = useState<'WIFI' | 'REMOTE'>('WIFI');
  const [isBroadcasting, setIsBroadcasting] = useState(false);
  const [roomCode, setRoomCode] = useState('--- ---');
  const [pin, setPin] = useState('----');
  const [serverUrl, setServerUrl] = useState('');
  const [viewersCount, setViewersCount] = useState(0);
  const [logs, setLogs] = useState<string[]>([]);
  const [localIp, setLocalIp] = useState('192.168.1.xxx');

  const generateRoomCode = () => {
    const c1 = Math.floor(100 + Math.random() * 900);
    const c2 = Math.floor(100 + Math.random() * 900);
    const p = Math.floor(1000 + Math.random() * 9000).toString();
    return { code: `${c1}-${c2}`, pin: p };
  };

  const toggleBroadcast = () => {
    if (!isBroadcasting) {
      if (activeMode === 'REMOTE') {
        const { code, pin: p } = generateRoomCode();
        setRoomCode(code);
        setPin(p);
        setIsBroadcasting(true);
        addLog(`[${new Date().toLocaleTimeString()}] 🔴 Started Remote Broadcast (Room ${code})`);
        addLog(`[${new Date().toLocaleTimeString()}] 📡 Server: ${serverUrl}`);
      } else {
        setIsBroadcasting(true);
        addLog(`[${new Date().toLocaleTimeString()}] 📶 Started Local Wi-Fi Stream`);
        addLog(`[${new Date().toLocaleTimeString()}] 🌐 URL: http://${localIp}:8080/stream`);
      }
    } else {
      setIsBroadcasting(false);
      setViewersCount(0);
      addLog(`[${new Date().toLocaleTimeString()}] ⏹ Stopped Streaming`);
    }
  };

  const addLog = (msg: string) => {
    setLogs(prev => [msg, ...prev.slice(0, 50)]);
  };

  const shareRoomCode = async () => {
    if (!isBroadcasting) return;
    try {
      await Share.share({
        message: `Join my AxeCast testing session! Room Code: ${roomCode} | PIN: ${pin} on AxeCast Studio (${APP_VERSION})`,
      });
    } catch (error) {
      console.error(error);
    }
  };

  return (
    <SafeAreaView style={styles.container}>
      <StatusBar barStyle="light-content" backgroundColor="#090d16" />

      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.title}>🪓 AxeCast Stream</Text>
        <View style={styles.versionBadge}>
          <Text style={styles.versionText}>{APP_VERSION}</Text>
        </View>
      </View>

      {/* Mode Selector Segmented Tabs */}
      <View style={styles.tabContainer}>
        <TouchableOpacity
          style={[styles.tabBtn, activeMode === 'WIFI' && styles.tabActiveWifi]}
          disabled={isBroadcasting}
          onPress={() => setActiveMode('WIFI')}
        >
          <Text style={[styles.tabText, activeMode === 'WIFI' && styles.tabTextActive]}>
            📶 Local Wi-Fi
          </Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={[styles.tabBtn, activeMode === 'REMOTE' && styles.tabActiveRemote]}
          disabled={isBroadcasting}
          onPress={() => setActiveMode('REMOTE')}
        >
          <Text style={[styles.tabText, activeMode === 'REMOTE' && styles.tabTextActive]}>
            🌐 Remote Room
          </Text>
        </TouchableOpacity>
      </View>

      {/* Tab 1: Local Wi-Fi Mode Card */}
      {activeMode === 'WIFI' && (
        <View style={styles.card}>
          <Text style={styles.cardSubtitle}>LOCAL WI-FI STREAM URL</Text>
          <Text style={styles.wifiUrlText}>http://{localIp}:8080/stream</Text>
          <Text style={styles.statusSubtext}>
            {isBroadcasting ? '🟢 Streaming on Local Wi-Fi' : '⚫ Ready to stream in same network'}
          </Text>
        </View>
      )}

      {/* Tab 2: Remote Room Mode Card */}
      {activeMode === 'REMOTE' && (
        <View style={styles.card}>
          <Text style={styles.cardSubtitle}>YOUR 6-DIGIT ROOM CODE</Text>
          <Text style={styles.roomCodeText}>{roomCode}</Text>
          <Text style={styles.pinText}>PIN: {pin}</Text>

          {isBroadcasting && (
            <TouchableOpacity style={styles.shareBtn} onPress={shareRoomCode}>
              <Text style={styles.shareBtnText}>📋 Share Code with Team</Text>
            </TouchableOpacity>
          )}

          {/* Server URL Input */}
          <View style={styles.inputGroup}>
            <Text style={styles.inputLabel}>📡 Relay Server URL:</Text>
            <TextInput
              style={styles.textInput}
              value={serverUrl}
              onChangeText={setServerUrl}
              editable={!isBroadcasting}
              placeholder="ws://192.168.1.108:9820"
              placeholderTextColor="#475569"
              autoCapitalize="none"
              autoCorrect={false}
            />
          </View>
        </View>
      )}

      {/* Status Badges */}
      <View style={styles.statusRow}>
        <View style={styles.badge}>
          <Text style={styles.badgeLabel}>Status:</Text>
          <Text style={[styles.badgeVal, isBroadcasting ? styles.textGreen : styles.textAmber]}>
            {isBroadcasting ? '🟢 Live' : '⚫ Idle'}
          </Text>
        </View>
        <View style={styles.badge}>
          <Text style={styles.badgeLabel}>Viewers:</Text>
          <Text style={styles.badgeVal}>👥 {viewersCount}</Text>
        </View>
        <View style={styles.badge}>
          <Text style={styles.badgeLabel}>FPS:</Text>
          <Text style={styles.badgeVal}>⚡ {isBroadcasting ? '60' : '0'}</Text>
        </View>
      </View>

      {/* Action Button */}
      <TouchableOpacity
        style={[styles.mainBtn, isBroadcasting ? styles.btnStop : styles.btnStart]}
        onPress={toggleBroadcast}
      >
        <Text style={styles.mainBtnText}>
          {isBroadcasting
            ? '⏹ Stop Streaming'
            : activeMode === 'WIFI'
            ? '📶 Start Wi-Fi Stream'
            : '🔴 Start Remote Broadcast'}
        </Text>
      </TouchableOpacity>

      {/* Live Logs Panel */}
      <View style={styles.logsContainer}>
        <View style={styles.logsHeader}>
          <Text style={styles.logsTitle}>📜 In-App Live Logs</Text>
          <TouchableOpacity onPress={() => setLogs([])}>
            <Text style={styles.clearText}>Clear</Text>
          </TouchableOpacity>
        </View>
        <ScrollView style={styles.logsScroll}>
          {logs.length === 0 ? (
            <Text style={styles.emptyLogs}>No logs yet. Tap Start to begin streaming.</Text>
          ) : (
            logs.map((log, index) => (
              <Text key={index} style={styles.logLine}>
                {log}
              </Text>
            ))
          )}
        </ScrollView>
      </View>

      {/* Footer */}
      <Text style={styles.footerText}>AxeCast Dual-Mode Companion Suite • {APP_VERSION}</Text>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#090d16',
    padding: 16,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 12,
    paddingHorizontal: 4,
  },
  title: {
    fontSize: 22,
    fontWeight: 'bold',
    color: '#38bdf8',
  },
  versionBadge: {
    backgroundColor: '#0369a1',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 6,
  },
  versionText: {
    color: '#ffffff',
    fontSize: 12,
    fontWeight: 'bold',
  },
  tabContainer: {
    flexDirection: 'row',
    backgroundColor: '#1e293b',
    borderRadius: 10,
    padding: 4,
    marginBottom: 14,
  },
  tabBtn: {
    flex: 1,
    paddingVertical: 8,
    alignItems: 'center',
    borderRadius: 8,
  },
  tabActiveWifi: {
    backgroundColor: '#0284c7',
  },
  tabActiveRemote: {
    backgroundColor: '#7c3aed',
  },
  tabText: {
    color: '#94a3b8',
    fontSize: 13,
    fontWeight: 'bold',
  },
  tabTextActive: {
    color: '#ffffff',
  },
  card: {
    backgroundColor: '#1e293b',
    borderRadius: 14,
    padding: 18,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#334155',
    marginBottom: 14,
  },
  cardSubtitle: {
    color: '#94a3b8',
    fontSize: 11,
    fontWeight: 'bold',
    letterSpacing: 1,
    marginBottom: 6,
  },
  wifiUrlText: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#38bdf8',
    marginVertical: 6,
  },
  statusSubtext: {
    color: '#f59e0b',
    fontSize: 12,
    marginTop: 4,
  },
  roomCodeText: {
    fontSize: 36,
    fontWeight: 'bold',
    color: '#ffffff',
    letterSpacing: 3,
  },
  pinText: {
    fontSize: 14,
    color: '#38bdf8',
    fontWeight: 'bold',
    marginTop: 2,
  },
  shareBtn: {
    marginTop: 10,
    backgroundColor: '#0284c7',
    paddingHorizontal: 14,
    paddingVertical: 6,
    borderRadius: 8,
  },
  shareBtnText: {
    color: '#ffffff',
    fontSize: 12,
    fontWeight: 'bold',
  },
  inputGroup: {
    width: '100%',
    marginTop: 12,
  },
  inputLabel: {
    color: '#94a3b8',
    fontSize: 11,
    fontWeight: 'bold',
    marginBottom: 4,
  },
  textInput: {
    backgroundColor: '#0f172a',
    borderRadius: 8,
    height: 40,
    paddingHorizontal: 12,
    color: '#ffffff',
    fontSize: 12,
    borderWidth: 1,
    borderColor: '#334155',
  },
  statusRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 14,
  },
  badge: {
    flex: 1,
    backgroundColor: '#0f172a',
    padding: 8,
    borderRadius: 8,
    marginHorizontal: 3,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#1e293b',
  },
  badgeLabel: {
    color: '#64748b',
    fontSize: 10,
  },
  badgeVal: {
    color: '#e2e8f0',
    fontSize: 12,
    fontWeight: 'bold',
    marginTop: 2,
  },
  textGreen: {
    color: '#22c55e',
  },
  textAmber: {
    color: '#f59e0b',
  },
  mainBtn: {
    height: 50,
    borderRadius: 10,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 14,
  },
  btnStart: {
    backgroundColor: '#16a34a',
  },
  btnStop: {
    backgroundColor: '#dc2626',
  },
  mainBtnText: {
    color: '#ffffff',
    fontSize: 15,
    fontWeight: 'bold',
  },
  logsContainer: {
    flex: 1,
    backgroundColor: '#0f172a',
    borderRadius: 10,
    padding: 10,
    borderWidth: 1,
    borderColor: '#1e293b',
  },
  logsHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 6,
  },
  logsTitle: {
    color: '#38bdf8',
    fontSize: 12,
    fontWeight: 'bold',
  },
  clearText: {
    color: '#64748b',
    fontSize: 11,
  },
  logsScroll: {
    flex: 1,
  },
  emptyLogs: {
    color: '#475569',
    fontSize: 11,
    fontStyle: 'italic',
    textAlign: 'center',
    marginTop: 16,
  },
  logLine: {
    color: '#94a3b8',
    fontFamily: 'monospace',
    fontSize: 10,
    marginBottom: 3,
  },
  footerText: {
    color: '#475569',
    fontSize: 10,
    textAlign: 'center',
    marginTop: 8,
  },
});
