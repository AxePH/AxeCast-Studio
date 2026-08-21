import React, { useState, useEffect } from 'react';
import {
  StyleSheet,
  Text,
  View,
  TouchableOpacity,
  ScrollView,
  StatusBar,
  SafeAreaView,
  Share,
} from 'react-native';

const APP_VERSION = 'v1.0.2';

export default function App() {
  const [isBroadcasting, setIsBroadcasting] = useState(false);
  const [roomCode, setRoomCode] = useState('--- ---');
  const [pin, setPin] = useState('----');
  const [viewersCount, setViewersCount] = useState(0);
  const [logs, setLogs] = useState<string[]>([]);
  const [serverStatus, setServerStatus] = useState('Ready');

  const generateRoomCode = () => {
    const c1 = Math.floor(100 + Math.random() * 900);
    const c2 = Math.floor(100 + Math.random() * 900);
    const p = Math.floor(1000 + Math.random() * 9000).toString();
    return { code: `${c1}-${c2}`, pin: p };
  };

  const toggleBroadcast = () => {
    if (!isBroadcasting) {
      const { code, pin: p } = generateRoomCode();
      setRoomCode(code);
      setPin(p);
      setIsBroadcasting(true);
      setServerStatus('Streaming to Room');
      addLog(`[${new Date().toLocaleTimeString()}] 🔴 Started Screen Broadcast`);
      addLog(`[${new Date().toLocaleTimeString()}] 🔑 Room Code: ${code} | PIN: ${p}`);
    } else {
      setIsBroadcasting(false);
      setServerStatus('Ready');
      setViewersCount(0);
      addLog(`[${new Date().toLocaleTimeString()}] ⏹ Stopped Broadcast`);
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

      {/* Room Display Card */}
      <View style={styles.card}>
        <Text style={styles.cardSubtitle}>YOUR 6-DIGIT ROOM CODE</Text>
        <Text style={styles.roomCodeText}>{roomCode}</Text>
        <Text style={styles.pinText}>PIN: {pin}</Text>

        {isBroadcasting && (
          <TouchableOpacity style={styles.shareBtn} onPress={shareRoomCode}>
            <Text style={styles.shareBtnText}>📋 Share Code with Team</Text>
          </TouchableOpacity>
        )}
      </View>

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

      {/* Big Action Button */}
      <TouchableOpacity
        style={[styles.mainBtn, isBroadcasting ? styles.btnStop : styles.btnStart]}
        onPress={toggleBroadcast}
      >
        <Text style={styles.mainBtnText}>
          {isBroadcasting ? '⏹ Stop Broadcast' : '🔴 Start Broadcast'}
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
            <Text style={styles.emptyLogs}>No logs yet. Tap Start Broadcast to begin.</Text>
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
      <Text style={styles.footerText}>AxeCast Mobile Companion Suite • {APP_VERSION}</Text>
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
    marginBottom: 16,
    paddingHorizontal: 8,
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
  card: {
    backgroundColor: '#1e293b',
    borderRadius: 16,
    padding: 20,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#334155',
    marginBottom: 16,
  },
  cardSubtitle: {
    color: '#94a3b8',
    fontSize: 12,
    fontWeight: 'bold',
    letterSpacing: 1,
    marginBottom: 8,
  },
  roomCodeText: {
    fontSize: 38,
    fontWeight: 'bold',
    color: '#ffffff',
    letterSpacing: 4,
  },
  pinText: {
    fontSize: 14,
    color: '#38bdf8',
    fontWeight: 'bold',
    marginTop: 4,
  },
  shareBtn: {
    marginTop: 12,
    backgroundColor: '#0284c7',
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 8,
  },
  shareBtnText: {
    color: '#ffffff',
    fontSize: 13,
    fontWeight: 'bold',
  },
  statusRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 16,
  },
  badge: {
    flex: 1,
    backgroundColor: '#0f172a',
    padding: 10,
    borderRadius: 8,
    marginHorizontal: 4,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#1e293b',
  },
  badgeLabel: {
    color: '#64748b',
    fontSize: 11,
  },
  badgeVal: {
    color: '#e2e8f0',
    fontSize: 13,
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
    height: 52,
    borderRadius: 12,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 16,
  },
  btnStart: {
    backgroundColor: '#16a34a',
  },
  btnStop: {
    backgroundColor: '#dc2626',
  },
  mainBtnText: {
    color: '#ffffff',
    fontSize: 16,
    fontWeight: 'bold',
  },
  logsContainer: {
    flex: 1,
    backgroundColor: '#0f172a',
    borderRadius: 12,
    padding: 12,
    borderWidth: 1,
    borderColor: '#1e293b',
  },
  logsHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },
  logsTitle: {
    color: '#38bdf8',
    fontSize: 13,
    fontWeight: 'bold',
  },
  clearText: {
    color: '#64748b',
    fontSize: 12,
  },
  logsScroll: {
    flex: 1,
  },
  emptyLogs: {
    color: '#475569',
    fontSize: 12,
    fontStyle: 'italic',
    textAlign: 'center',
    marginTop: 20,
  },
  logLine: {
    color: '#94a3b8',
    fontFamily: 'monospace',
    fontSize: 11,
    marginBottom: 4,
  },
  footerText: {
    color: '#475569',
    fontSize: 11,
    textAlign: 'center',
    marginTop: 12,
  },
});
