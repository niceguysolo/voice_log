/**
 * Voice Log App - React Native Frontend
 * Simple, elderly-friendly interface
 * 
 * This app connects to your Python backend
 */

import React, { useState, useEffect } from 'react';
import {
  SafeAreaView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
  ScrollView,
  Alert,
  ActivityIndicator,
  Platform,
} from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Audio } from 'expo-av';
import * as Google from 'expo-auth-session/providers/google';
import * as WebBrowser from 'expo-web-browser';

// Your Python backend URL
const API_URL = 'http://localhost:8000'; // Change to your deployed URL

// Complete the auth session
WebBrowser.maybeCompleteAuthSession();

const App = () => {
  // State management
  const [user, setUser] = useState(null);
  const [accessToken, setAccessToken] = useState(null);
  const [recording, setRecording] = useState(null);
  const [isRecording, setIsRecording] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [recentLogs, setRecentLogs] = useState([]);
  const [playingSound, setPlayingSound] = useState(null);

  // Google Sign-In configuration
  const [request, response, promptAsync] = Google.useAuthRequest({
    expoClientId: 'YOUR_EXPO_CLIENT_ID',
    iosClientId: 'YOUR_IOS_CLIENT_ID',
    androidClientId: 'YOUR_ANDROID_CLIENT_ID',
    webClientId: 'YOUR_WEB_CLIENT_ID',
  });

  // Handle Google Sign-In response
  useEffect(() => {
    if (response?.type === 'success') {
      const { id_token } = response.params;
      signInWithBackend(id_token);
    }
  }, [response]);

  // Load saved session on app start
  useEffect(() => {
    loadSession();
  }, []);

  // Load logs when user signs in
  useEffect(() => {
    if (accessToken) {
      loadRecentLogs();
    }
  }, [accessToken]);

  // ============================================================================
  // AUTHENTICATION FUNCTIONS
  // ============================================================================

  const loadSession = async () => {
    try {
      const savedToken = await AsyncStorage.getItem('accessToken');
      const savedUser = await AsyncStorage.getItem('user');
      
      if (savedToken && savedUser) {
        setAccessToken(savedToken);
        setUser(JSON.parse(savedUser));
      }
    } catch (error) {
      console.error('Error loading session:', error);
    }
  };

  const signInWithBackend = async (googleToken) => {
    try {
      const response = await fetch(`${API_URL}/auth/google`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ token: googleToken }),
      });

      const data = await response.json();
      
      if (response.ok) {
        setAccessToken(data.access_token);
        setUser(data.user);
        
        // Save to storage
        await AsyncStorage.setItem('accessToken', data.access_token);
        await AsyncStorage.setItem('user', JSON.stringify(data.user));
        
        Alert.alert('Success', 'Signed in successfully!');
      } else {
        Alert.alert('Error', 'Failed to sign in');
      }
    } catch (error) {
      console.error('Sign in error:', error);
      Alert.alert('Error', 'Network error. Please try again.');
    }
  };

  const signOut = async () => {
    await AsyncStorage.removeItem('accessToken');
    await AsyncStorage.removeItem('user');
    setAccessToken(null);
    setUser(null);
    setRecentLogs([]);
  };

  // ============================================================================
  // VOICE RECORDING FUNCTIONS
  // ============================================================================

  const startRecording = async () => {
    try {
      // Request permissions
      const permission = await Audio.requestPermissionsAsync();
      if (!permission.granted) {
        Alert.alert('Permission Required', 'Please allow microphone access');
        return;
      }

      // Configure audio mode
      await Audio.setAudioModeAsync({
        allowsRecordingIOS: true,
        playsInSilentModeIOS: true,
      });

      // Start recording
      const { recording } = await Audio.Recording.createAsync(
        Audio.RecordingOptionsPresets.HIGH_QUALITY
      );

      setRecording(recording);
      setIsRecording(true);
    } catch (error) {
      console.error('Failed to start recording:', error);
      Alert.alert('Error', 'Could not start recording');
    }
  };

  const stopRecording = async () => {
    if (!recording) return;

    try {
      setIsRecording(false);
      setIsProcessing(true);

      await recording.stopAndUnloadAsync();
      const uri = recording.getURI();

      // Send to backend
      await uploadRecording(uri);

      setRecording(null);
    } catch (error) {
      console.error('Failed to stop recording:', error);
      Alert.alert('Error', 'Could not process recording');
    } finally {
      setIsProcessing(false);
    }
  };

  const uploadRecording = async (uri) => {
    try {
      // Read file as base64
      const response = await fetch(uri);
      const blob = await response.blob();
      const reader = new FileReader();
      
      reader.onloadend = async () => {
        const base64Audio = reader.result.split(',')[1];

        // Send to backend
        const uploadResponse = await fetch(`${API_URL}/logs`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${accessToken}`,
          },
          body: JSON.stringify({
            audio_base64: base64Audio,
            timestamp: new Date().toISOString(),
          }),
        });

        const data = await uploadResponse.json();

        if (uploadResponse.ok) {
          Alert.alert('Success', `Logged: "${data.transcription}"`);
          loadRecentLogs(); // Refresh logs
        } else {
          Alert.alert('Error', 'Failed to save log');
        }
      };

      reader.readAsDataURL(blob);
    } catch (error) {
      console.error('Upload error:', error);
      Alert.alert('Error', 'Failed to upload recording');
    }
  };

  // ============================================================================
  // LOG MANAGEMENT FUNCTIONS
  // ============================================================================

  const loadRecentLogs = async () => {
    try {
      const response = await fetch(`${API_URL}/logs?days=7`, {
        headers: {
          'Authorization': `Bearer ${accessToken}`,
        },
      });

      const data = await response.json();
      if (response.ok) {
        setRecentLogs(data);
      }
    } catch (error) {
      console.error('Error loading logs:', error);
    }
  };

  // ============================================================================
  // AI QUESTION FUNCTIONS
  // ============================================================================

  const askQuestion = async (question) => {
    setIsProcessing(true);

    try {
      const response = await fetch(`${API_URL}/ask`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${accessToken}`,
        },
        body: JSON.stringify({
          question,
          voice_response: true,
        }),
      });

      const data = await response.json();

      if (response.ok) {
        // Show text answer
        Alert.alert('Answer', data.answer_text);

        // Play audio if available
        if (data.answer_audio_url) {
          await playAudio(data.answer_audio_url);
        }
      } else {
        Alert.alert('Error', 'Could not get answer');
      }
    } catch (error) {
      console.error('Question error:', error);
      Alert.alert('Error', 'Network error');
    } finally {
      setIsProcessing(false);
    }
  };

  const playAudio = async (url) => {
    try {
      const { sound } = await Audio.Sound.createAsync({ uri: url });
      setPlayingSound(sound);
      await sound.playAsync();

      // Cleanup when done
      sound.setOnPlaybackStatusUpdate((status) => {
        if (status.didJustFinish) {
          sound.unloadAsync();
          setPlayingSound(null);
        }
      });
    } catch (error) {
      console.error('Audio playback error:', error);
    }
  };

  // Quick question buttons for elderly users
  const quickQuestions = [
    "Did I take my medication today?",
    "What did I eat yesterday?",
    "What activities did I do this week?",
    "When was my last doctor visit?",
  ];

  // ============================================================================
  // RENDER
  // ============================================================================

  // Sign-in screen
  if (!user) {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.signInContainer}>
          <Text style={styles.title}>Voice Log</Text>
          <Text style={styles.subtitle}>Your Daily Memory Assistant</Text>

          <TouchableOpacity
            style={styles.signInButton}
            onPress={() => promptAsync()}
            disabled={!request}
          >
            <Text style={styles.signInButtonText}>
              Sign in with Google
            </Text>
          </TouchableOpacity>

          <Text style={styles.helpText}>
            Simple voice logging for tracking your daily activities
          </Text>
        </View>
      </SafeAreaView>
    );
  }

  // Main app screen
  return (
    <SafeAreaView style={styles.container}>
      <ScrollView style={styles.scrollView}>
        {/* Header */}
        <View style={styles.header}>
          <Text style={styles.greeting}>Hello, {user.name}!</Text>
          <TouchableOpacity onPress={signOut}>
            <Text style={styles.signOutButton}>Sign Out</Text>
          </TouchableOpacity>
        </View>

        {/* Record Button */}
        <View style={styles.recordSection}>
          <TouchableOpacity
            style={[
              styles.recordButton,
              isRecording && styles.recordButtonActive,
            ]}
            onPress={isRecording ? stopRecording : startRecording}
            disabled={isProcessing}
          >
            <Text style={styles.recordButtonText}>
              {isRecording ? '⏹️ STOP' : '🎤 RECORD'}
            </Text>
            <Text style={styles.recordButtonSubtext}>
              {isRecording
                ? 'Tap to stop recording'
                : 'Tap to log your activity'}
            </Text>
          </TouchableOpacity>

          {isProcessing && (
            <ActivityIndicator size="large" color="#007AFF" style={styles.spinner} />
          )}
        </View>

        {/* Quick Questions */}
        <View style={styles.questionsSection}>
          <Text style={styles.sectionTitle}>Ask a Question</Text>
          {quickQuestions.map((question, index) => (
            <TouchableOpacity
              key={index}
              style={styles.questionButton}
              onPress={() => askQuestion(question)}
              disabled={isProcessing}
            >
              <Text style={styles.questionButtonText}>{question}</Text>
            </TouchableOpacity>
          ))}
        </View>

        {/* Recent Logs */}
        <View style={styles.logsSection}>
          <Text style={styles.sectionTitle}>Recent Activities</Text>
          {recentLogs.length === 0 ? (
            <Text style={styles.noLogsText}>
              No activities yet. Start by recording your first log!
            </Text>
          ) : (
            recentLogs.slice(0, 5).map((log) => (
              <View key={log.id} style={styles.logItem}>
                <Text style={styles.logTime}>
                  {new Date(log.timestamp).toLocaleDateString()} at{' '}
                  {new Date(log.timestamp).toLocaleTimeString()}
                </Text>
                <Text style={styles.logText}>{log.transcription}</Text>
              </View>
            ))
          )}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
};

// ============================================================================
// STYLES - Optimized for elderly users (large text, high contrast)
// ============================================================================

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#FFFFFF',
  },
  scrollView: {
    flex: 1,
  },
  
  // Sign-in screen
  signInContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 30,
  },
  title: {
    fontSize: 48,
    fontWeight: 'bold',
    color: '#000000',
    marginBottom: 10,
  },
  subtitle: {
    fontSize: 24,
    color: '#666666',
    marginBottom: 50,
    textAlign: 'center',
  },
  signInButton: {
    backgroundColor: '#4285F4',
    paddingVertical: 20,
    paddingHorizontal: 40,
    borderRadius: 15,
    marginBottom: 30,
  },
  signInButtonText: {
    color: '#FFFFFF',
    fontSize: 24,
    fontWeight: 'bold',
  },
  helpText: {
    fontSize: 18,
    color: '#999999',
    textAlign: 'center',
    paddingHorizontal: 30,
  },
  
  // Main screen header
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 20,
    borderBottomWidth: 2,
    borderBottomColor: '#EEEEEE',
  },
  greeting: {
    fontSize: 28,
    fontWeight: 'bold',
    color: '#000000',
  },
  signOutButton: {
    fontSize: 18,
    color: '#007AFF',
  },
  
  // Record section
  recordSection: {
    alignItems: 'center',
    paddingVertical: 40,
  },
  recordButton: {
    width: 280,
    height: 280,
    borderRadius: 140,
    backgroundColor: '#FF3B30',
    justifyContent: 'center',
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 5,
    elevation: 8,
  },
  recordButtonActive: {
    backgroundColor: '#FF9500',
  },
  recordButtonText: {
    fontSize: 36,
    fontWeight: 'bold',
    color: '#FFFFFF',
    marginBottom: 10,
  },
  recordButtonSubtext: {
    fontSize: 18,
    color: '#FFFFFF',
    textAlign: 'center',
    paddingHorizontal: 20,
  },
  spinner: {
    marginTop: 20,
  },
  
  // Questions section
  questionsSection: {
    padding: 20,
  },
  sectionTitle: {
    fontSize: 28,
    fontWeight: 'bold',
    color: '#000000',
    marginBottom: 15,
  },
  questionButton: {
    backgroundColor: '#007AFF',
    padding: 20,
    borderRadius: 12,
    marginBottom: 12,
  },
  questionButtonText: {
    fontSize: 20,
    color: '#FFFFFF',
    fontWeight: '600',
  },
  
  // Logs section
  logsSection: {
    padding: 20,
    paddingBottom: 40,
  },
  noLogsText: {
    fontSize: 20,
    color: '#999999',
    textAlign: 'center',
    padding: 30,
  },
  logItem: {
    backgroundColor: '#F5F5F5',
    padding: 20,
    borderRadius: 12,
    marginBottom: 12,
  },
  logTime: {
    fontSize: 16,
    color: '#666666',
    marginBottom: 8,
  },
  logText: {
    fontSize: 20,
    color: '#000000',
    lineHeight: 28,
  },
});

export default App;
