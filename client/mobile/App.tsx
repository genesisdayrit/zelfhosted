import { StatusBar } from 'expo-status-bar';
import { useState, useRef } from 'react';
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

interface Message {
  role: 'user' | 'assistant';
  content: string;
}

export default function App() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const listRef = useRef<FlatList>(null);

  const handleSubmit = () => {
    if (!input.trim() || isStreaming) return;

    const userMessage = input.trim();
    setInput('');
    setMessages(prev => [...prev, { role: 'user', content: userMessage }]);

    // Mock assistant response for now
    setIsStreaming(true);
    setMessages(prev => [...prev, { role: 'assistant', content: '' }]);

    // Simulate streaming response
    const mockResponse = 'This is a mock response. API integration coming in a future milestone!';
    let charIndex = 0;

    const interval = setInterval(() => {
      if (charIndex < mockResponse.length) {
        setMessages(prev => {
          const updated = [...prev];
          const lastMsg = updated[updated.length - 1];
          if (lastMsg?.role === 'assistant') {
            lastMsg.content = mockResponse.slice(0, charIndex + 1);
          }
          return updated;
        });
        charIndex++;
      } else {
        clearInterval(interval);
        setIsStreaming(false);
      }
    }, 30);
  };

  const handleClear = () => {
    setMessages([]);
    setInput('');
    setIsStreaming(false);
  };

  const renderMessage = ({ item, index }: { item: Message; index: number }) => {
    const isUser = item.role === 'user';
    const isLastMessage = index === messages.length - 1;

    return (
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
    borderBottomColor: `${COLORS.purple500}4D`, // 30% opacity
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
    gap: 16,
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

  // Messages
  message: {
    borderLeftWidth: 2,
    paddingLeft: 12,
    marginBottom: 16,
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
