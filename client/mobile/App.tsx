import { StatusBar } from 'expo-status-bar';
import { useState, useRef, useEffect } from 'react';
import * as Location from 'expo-location';
import {
  StyleSheet,
  Text,
  View,
  TextInput,
  TouchableOpacity,
  FlatList,
  KeyboardAvoidingView,
  Platform,
  SafeAreaView,
} from 'react-native';

// API URL from environment variable, fallback to localhost for web dev
const API_URL = process.env.EXPO_PUBLIC_API_URL || 'http://localhost:8000';

// Theme colors (matching Next.js app)
const COLORS = {
  bg: '#1a1612',
  bgDark: '#0f0d0a',
  sand200: '#e8dcc4',
  sand300: '#d4a574',
  sand400: '#8b7355',
  purple500: '#8b5cf6',
  green500: '#22c55e',
  red500: '#ef4444',
  cyan500: '#06b6d4',
  amber500: '#f59e0b',
};

const ZELF_LOGO = `
  ╔═══════════════════════════╗
  ║                           ║
  ║     ░▀▀█░█▀▀░█░░░█▀▀░     ║
  ║     ░▄▀░░█▀▀░█░░░█▀░░     ║
  ║     ░▀▀▀░▀▀▀░▀▀▀░▀░░░     ║
  ║                           ║
  ╚═══════════════════════════╝
`;

// Tool icons (matching Next.js app)
const TOOL_ICONS: Record<string, string> = {
  get_weather: '🌤️',
  get_polymarket_opportunities: '📈',
  get_arxiv_articles: '📚',
  get_latest_photos: '📷',
  search_youtube_song: '🎵',
  default: '⚡',
};

interface Message {
  role: 'user' | 'assistant';
  content: string;
}

interface TraceEvent {
  id: string;
  type: 'node' | 'tool';
  name: string;
  status: 'running' | 'complete';
  args?: Record<string, unknown>;
  result?: string;
}

interface UserLocation {
  lat: number;
  lon: number;
}

export default function App() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [traceEvents, setTraceEvents] = useState<TraceEvent[]>([]);
  const [userLocation, setUserLocation] = useState<UserLocation | null>(null);
  const listRef = useRef<FlatList>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  // Request location permission and get location on mount
  useEffect(() => {
    (async () => {
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== 'granted') {
        // User denied permission - that's fine, location is optional
        console.log('Location permission denied');
        return;
      }

      try {
        const location = await Location.getCurrentPositionAsync({
          accuracy: Location.Accuracy.Balanced,
        });
        setUserLocation({
          lat: location.coords.latitude,
          lon: location.coords.longitude,
        });
        console.log('Location acquired:', location.coords.latitude, location.coords.longitude);
      } catch (error) {
        console.log('Error getting location:', error);
      }
    })();
  }, []);

  const handleSubmit = async () => {
    if (!input.trim() || isStreaming) return;

    const userMessage = input.trim();
    setInput('');
    setMessages(prev => [...prev, { role: 'user', content: userMessage }]);
    setIsStreaming(true);
    setTraceEvents([]);
    setMessages(prev => [...prev, { role: 'assistant', content: '' }]);

    abortControllerRef.current = new AbortController();
    let accumulatedContent = '';

    try {
      const response = await fetch(`${API_URL}/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: userMessage,
          location: userLocation,
        }),
        signal: abortControllerRef.current.signal,
      });

      if (!response.ok) throw new Error('Failed to fetch');

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();

      if (!reader) throw new Error('No reader available');

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value);
        const lines = chunk.split('\n');

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));

              if (data.type === 'node_start') {
                setTraceEvents(prev => [
                  ...prev,
                  {
                    id: `node-${data.node}-${Date.now()}`,
                    type: 'node',
                    name: data.node,
                    status: 'running',
                  },
                ]);
              } else if (data.type === 'tool_call') {
                setTraceEvents(prev => [
                  ...prev,
                  {
                    id: `tool-${data.tool}-${Date.now()}`,
                    type: 'tool',
                    name: data.tool,
                    status: 'running',
                    args: data.args,
                  },
                ]);
              } else if (data.type === 'tool_result') {
                setTraceEvents(prev =>
                  prev.map(event =>
                    event.type === 'tool' &&
                    event.name === data.tool &&
                    event.status === 'running'
                      ? { ...event, status: 'complete', result: data.result }
                      : event
                  )
                );
              } else if (data.type === 'token') {
                accumulatedContent += data.content;
                setMessages(prev => {
                  const updated = [...prev];
                  const lastMsg = updated[updated.length - 1];
                  if (lastMsg?.role === 'assistant') {
                    lastMsg.content = accumulatedContent;
                  }
                  return updated;
                });
              } else if (data.type === 'node_complete') {
                setTraceEvents(prev =>
                  prev.map(event =>
                    event.type === 'node' &&
                    event.name === data.node &&
                    event.status === 'running'
                      ? { ...event, status: 'complete' }
                      : event
                  )
                );
              } else if (data.type === 'done') {
                setIsStreaming(false);
              }
            } catch {
              // Skip invalid JSON
            }
          }
        }
      }
    } catch (error) {
      if ((error as Error).name === 'AbortError') {
        return;
      }
      console.error('Error:', error);
      setMessages(prev => {
        const updated = [...prev];
        const lastMsg = updated[updated.length - 1];
        if (lastMsg?.role === 'assistant') {
          lastMsg.content = 'ERROR: Connection failed. Make sure the server is running.';
        }
        return updated;
      });
    } finally {
      setIsStreaming(false);
    }
  };

  const handleClear = () => {
    if (isStreaming) {
      abortControllerRef.current?.abort();
    }
    setMessages([]);
    setInput('');
    setIsStreaming(false);
    setTraceEvents([]);
  };

  const renderTraceEvents = () => {
    if (traceEvents.length === 0) return null;

    return (
      <View style={styles.traceContainer}>
        <Text style={styles.traceLabel}>[TRACE]</Text>
        <View style={styles.traceFlow}>
          {traceEvents.map((event, i) => (
            <View key={event.id} style={styles.traceItem}>
              {i > 0 && <Text style={styles.traceArrow}>→</Text>}
              <View
                style={[
                  styles.traceBadge,
                  event.type === 'node'
                    ? event.status === 'running'
                      ? styles.nodeRunning
                      : styles.nodeComplete
                    : event.status === 'running'
                    ? styles.toolRunning
                    : styles.toolComplete,
                ]}
              >
                {event.type === 'tool' && (
                  <Text style={styles.traceIcon}>
                    {TOOL_ICONS[event.name] || TOOL_ICONS.default}
                  </Text>
                )}
                <Text
                  style={[
                    styles.traceName,
                    event.type === 'node'
                      ? event.status === 'running'
                        ? styles.nodeRunningText
                        : styles.nodeCompleteText
                      : event.status === 'running'
                      ? styles.toolRunningText
                      : styles.toolCompleteText,
                  ]}
                >
                  {event.name}
                </Text>
                <Text style={styles.traceStatus}>
                  {event.status === 'running' ? '●' : '✓'}
                </Text>
              </View>
            </View>
          ))}
        </View>
      </View>
    );
  };

  const renderMessage = ({ item, index }: { item: Message; index: number }) => {
    const isUser = item.role === 'user';
    const isLastMessage = index === messages.length - 1;

    return (
      <View style={styles.messageWrapper}>
        {/* Show trace events above the last assistant message */}
        {!isUser && isLastMessage && renderTraceEvents()}

        <View
          style={[
            styles.message,
            isUser ? styles.userBorder : styles.assistantBorder,
          ]}
        >
          <View style={styles.messageHeader}>
            <Text style={isUser ? styles.userLabel : styles.assistantLabel}>
              {isUser ? 'USER' : 'SYSTEM'}
            </Text>
            <Text style={styles.timestamp}>
              {new Date().toLocaleTimeString()}
            </Text>
          </View>
          <Text style={styles.messageContent}>
            {item.content}
            {!isUser && isStreaming && isLastMessage && (
              <Text style={styles.cursor}>▋</Text>
            )}
          </Text>
        </View>
      </View>
    );
  };

  const renderWelcome = () => (
    <View style={styles.welcome}>
      <Text style={styles.logo}>{ZELF_LOGO}</Text>
      <Text style={styles.ready}>{'>'} SYSTEM READY. ENTER QUERY TO BEGIN_</Text>
      <Text style={styles.version}>[LangGraph Neural Interface v0.1.0]</Text>
    </View>
  );

  return (
    <SafeAreaView style={styles.container}>
      <StatusBar style="light" />

      {/* Header */}
      <View style={styles.header}>
        <View style={styles.dots}>
          <TouchableOpacity
            style={[styles.dot, styles.dotRed]}
            onPress={handleClear}
          />
          <View style={[styles.dot, styles.dotYellow]} />
          <View style={[styles.dot, styles.dotGreen]} />
        </View>
        <Text style={styles.prompt}>zelfhosted@terminal:~$</Text>
        <Text style={styles.headerCursor}>▋</Text>
      </View>

      {/* Messages */}
      <KeyboardAvoidingView
        style={styles.content}
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        keyboardVerticalOffset={0}
      >
        <FlatList
          ref={listRef}
          data={messages}
          keyExtractor={(_, index) => index.toString()}
          renderItem={renderMessage}
          ListEmptyComponent={renderWelcome}
          contentContainerStyle={messages.length === 0 ? styles.emptyList : styles.messageList}
          onContentSizeChange={() => listRef.current?.scrollToEnd({ animated: true })}
          onLayout={() => listRef.current?.scrollToEnd({ animated: false })}
        />

        {/* Input */}
        <View style={styles.inputContainer}>
          <View style={styles.inputWrapper}>
            <Text style={styles.inputPrompt}>{'>'}</Text>
            <TextInput
              style={styles.input}
              value={input}
              onChangeText={setInput}
              placeholder="Enter command..."
              placeholderTextColor={COLORS.sand400}
              onSubmitEditing={handleSubmit}
              returnKeyType="send"
              editable={!isStreaming}
              autoCapitalize="none"
              autoCorrect={false}
            />
            {isStreaming ? (
              <Text style={styles.processing}>PROCESSING</Text>
            ) : (
              <TouchableOpacity
                onPress={handleSubmit}
                disabled={!input.trim()}
                style={!input.trim() ? styles.enterDisabled : undefined}
              >
                <Text style={styles.enterButton}>[ENTER]</Text>
              </TouchableOpacity>
            )}
          </View>
          <Text style={styles.hint}>Press ENTER to execute</Text>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: COLORS.bg,
  },

  // Header
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: 2,
    borderBottomColor: `${COLORS.purple500}4D`,
  },
  dots: {
    flexDirection: 'row',
    gap: 6,
    marginRight: 12,
  },
  dot: {
    width: 12,
    height: 12,
    borderRadius: 6,
  },
  dotRed: {
    backgroundColor: COLORS.red500,
  },
  dotYellow: {
    backgroundColor: COLORS.sand300,
  },
  dotGreen: {
    backgroundColor: COLORS.green500,
  },
  prompt: {
    color: COLORS.sand300,
    fontSize: 14,
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
  },
  headerCursor: {
    color: COLORS.green500,
    marginLeft: 4,
  },

  // Content
  content: {
    flex: 1,
  },
  emptyList: {
    flex: 1,
    justifyContent: 'center',
  },
  messageList: {
    padding: 16,
  },

  // Welcome screen
  welcome: {
    alignItems: 'center',
    justifyContent: 'center',
    padding: 20,
  },
  logo: {
    color: COLORS.purple500,
    fontSize: 10,
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
    marginBottom: 24,
  },
  ready: {
    color: COLORS.sand300,
    fontSize: 14,
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
  },
  version: {
    color: COLORS.sand400,
    fontSize: 12,
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
    marginTop: 8,
  },

  // Trace events
  traceContainer: {
    borderLeftWidth: 2,
    borderLeftColor: `${COLORS.purple500}80`,
    paddingLeft: 12,
    marginBottom: 12,
  },
  traceLabel: {
    color: COLORS.sand400,
    fontSize: 10,
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
    marginBottom: 8,
  },
  traceFlow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    gap: 4,
  },
  traceItem: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  traceArrow: {
    color: COLORS.sand400,
    marginHorizontal: 4,
    fontSize: 12,
  },
  traceBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 4,
    borderWidth: 1,
    gap: 4,
  },
  nodeRunning: {
    borderColor: COLORS.sand300,
    backgroundColor: `${COLORS.sand300}1A`,
  },
  nodeComplete: {
    borderColor: COLORS.green500,
    backgroundColor: `${COLORS.green500}1A`,
  },
  toolRunning: {
    borderColor: COLORS.amber500,
    backgroundColor: `${COLORS.amber500}1A`,
  },
  toolComplete: {
    borderColor: COLORS.cyan500,
    backgroundColor: `${COLORS.cyan500}1A`,
  },
  traceIcon: {
    fontSize: 12,
  },
  traceName: {
    fontSize: 10,
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
  },
  nodeRunningText: {
    color: COLORS.sand300,
  },
  nodeCompleteText: {
    color: COLORS.green500,
  },
  toolRunningText: {
    color: COLORS.amber500,
  },
  toolCompleteText: {
    color: COLORS.cyan500,
  },
  traceStatus: {
    fontSize: 10,
  },

  // Messages
  messageWrapper: {
    marginBottom: 16,
  },
  message: {
    borderLeftWidth: 2,
    paddingLeft: 12,
  },
  userBorder: {
    borderLeftColor: COLORS.purple500,
  },
  assistantBorder: {
    borderLeftColor: COLORS.green500,
  },
  messageHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 4,
  },
  userLabel: {
    color: COLORS.purple500,
    fontSize: 12,
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
    fontWeight: '600',
  },
  assistantLabel: {
    color: COLORS.green500,
    fontSize: 12,
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
    fontWeight: '600',
  },
  timestamp: {
    color: COLORS.sand400,
    fontSize: 12,
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
  },
  messageContent: {
    color: COLORS.sand200,
    fontSize: 14,
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
    lineHeight: 22,
  },
  cursor: {
    color: COLORS.green500,
  },

  // Input
  inputContainer: {
    borderTopWidth: 2,
    borderTopColor: `${COLORS.purple500}4D`,
    padding: 16,
    backgroundColor: COLORS.bg,
  },
  inputWrapper: {
    flexDirection: 'row',
    alignItems: 'center',
    borderWidth: 2,
    borderColor: `${COLORS.purple500}80`,
    borderRadius: 4,
    backgroundColor: COLORS.bgDark,
    paddingHorizontal: 12,
    paddingVertical: 10,
    gap: 8,
  },
  inputPrompt: {
    color: COLORS.green500,
    fontSize: 16,
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
  },
  input: {
    flex: 1,
    color: COLORS.sand200,
    fontSize: 14,
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
    padding: 0,
  },
  enterButton: {
    color: COLORS.purple500,
    fontSize: 12,
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
  },
  enterDisabled: {
    opacity: 0.3,
  },
  processing: {
    color: COLORS.sand300,
    fontSize: 12,
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
  },
  hint: {
    color: COLORS.sand400,
    fontSize: 12,
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
    textAlign: 'center',
    marginTop: 8,
  },
});
