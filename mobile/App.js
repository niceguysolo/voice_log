/**
 * Voice Log App - Updated with Voice & Text Input
 * Record activities and ask questions using voice OR text
 * Pleasant feminine voice for responses
 */

import React, { useState, useEffect } from 'react';
import {
  SafeAreaView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
  ScrollView,
  ActivityIndicator,
  Alert,
} from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Audio } from 'expo-av';
import * as Google from 'expo-auth-session/providers/google';
import * as WebBrowser from 'expo-web-browser';

// API Configuration
const API_URL = 'http://localhost:8000'; // Change to your Railway URL

// Voice preference - pleasant feminine voice
const VOICE_PREFERENCE = 'female_gentle'; // Options: female_gentle, female_energetic

WebBrowser.maybeCompleteAuthSession();

const App = () => {
  // State
  const [user, setUser] = useState(null);
  const [accessToken, setAccessToken] = useState(null);
  const [recording, setRecording] = useState(null);
  const [questionRecording, setQuestionRecording] = useState(null);
  const [isRecording, setIsRecording] = useState(false);
  const [isQuestionRecording, setIsQuestionRecording] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [recentLogs, setRecentLogs] = useState([]);
  const [playingSound, setPlayingSound] = useState(null);
  
  // Input mode state
  const [recordMode, setRecordMode] = useState('voice'); // 'voice' or 'text'
  const [questionMode, setQuestionMode] = useState('text'); // 'text' or 'voice'
  
  // Text input state
  const [activityText, setActivityText] = useState('');
  const [questionText, setQuestionText] = useState('');
  const [answerData, setAnswerData] = useState(null);

  // Google Sign-In
  const [request, response, promptAsync] = Google.useAuthRequest({
    expoClientId: 'YOUR_EXPO_CLIENT_ID',
    iosClientId: 'YOUR_IOS_CLIENT_ID',
    androidClientId: 'YOUR_ANDROID_CLIENT_ID',
    webClientId: 'YOUR_WEB_CLIENT_ID',
  });

  useEffect(() => {
    if (response?.type === 'success') {
      const { id_token } = response.params;
      signInWithBackend(id_token);
    }
  }, [response]);

  useEffect(() => {
    loadSession();
  }, []);

  useEffect(() => {
    if (accessToken) {
      loadRecentLogs();
    }
  }, [accessToken]);

  // ============================================================================
  // AUTHENTICATION
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
  // VOICE RECORDING (Activity)
  // ============================================================================

  const startRecording = async () => {
    try {
      const permission = await Audio.requestPermissionsAsync();
      if (!permission.granted) {
        Alert.alert('Permission Required', 'Please allow microphone access');
        return;
      }

      await Audio.setAudioModeAsync({
        allowsRecordingIOS: true,
        playsInSilentModeIOS: true,
      });

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
      const response = await fetch(uri);
      const blob = await response.blob();
      const reader = new FileReader();
      
      reader.onloadend = async () => {
        const base64Audio = reader.result.split(',')[1];

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
          loadRecentLogs();
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
  // TEXT ACTIVITY SUBMISSION
  // ============================================================================

  const submitTextActivity = async () => {
    if (!activityText.trim()) {
      Alert.alert('Empty Text', 'Please enter an activity description');
      return;
    }

    setIsProcessing(true);

    try {
      const response = await fetch(`${API_URL}/logs/text`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${accessToken}`,
        },
        body: JSON.stringify({
          text: activityText,
          timestamp: new Date().toISOString(),
        }),
      });

      if (response.ok) {
        Alert.alert('Success', 'Activity logged!');
        setActivityText('');
        loadRecentLogs();
      } else {
        Alert.alert('Error', 'Failed to save activity');
      }
    } catch (error) {
      console.error('Error:', error);
      Alert.alert('Error', 'Network error');
    } finally {
      setIsProcessing(false);
    }
  };

  // ============================================================================
  // VOICE QUESTION RECORDING
  // ============================================================================

  const startQuestionRecording = async () => {
    try {
      const permission = await Audio.requestPermissionsAsync();
      if (!permission.granted) {
        Alert.alert('Permission Required', 'Please allow microphone access');
        return;
      }

      await Audio.setAudioModeAsync({
        allowsRecordingIOS: true,
        playsInSilentModeIOS: true,
      });

      const { recording } = await Audio.Recording.createAsync(
        Audio.RecordingOptionsPresets.HIGH_QUALITY
      );

      setQuestionRecording(recording);
      setIsQuestionRecording(true);
    } catch (error) {
      console.error('Failed to start recording:', error);
      Alert.alert('Error', 'Could not start recording');
    }
  };

  const stopQuestionRecording = async () => {
    if (!questionRecording) return;

    try {
      setIsQuestionRecording(false);
      setIsProcessing(true);

      await questionRecording.stopAndUnloadAsync();
      const uri = questionRecording.getURI();

      await processQuestionRecording(uri);

      setQuestionRecording(null);
    } catch (error) {
      console.error('Failed to stop recording:', error);
      Alert.alert('Error', 'Could not process recording');
    } finally {
      setIsProcessing(false);
    }
  };

  const processQuestionRecording = async (uri) => {
    try {
      const response = await fetch(uri);
      const blob = await response.blob();
      const reader = new FileReader();
      
      reader.onloadend = async () => {
        const base64Audio = reader.result.split(',')[1];

        // First transcribe the question
        const transcribeResponse = await fetch(`${API_URL}/transcribe`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${accessToken}`,
          },
          body: JSON.stringify({
            audio_base64: base64Audio,
          }),
        });

        if (!transcribeResponse.ok) {
          Alert.alert('Error', 'Failed to transcribe question');
          return;
        }

        const transcribeData = await transcribeResponse.json();
        setQuestionText(transcribeData.text);
        
        // Now ask the question
        await askQuestion(transcribeData.text);
      };

      reader.readAsDataURL(blob);
    } catch (error) {
      console.error('Error:', error);
      Alert.alert('Error', 'Failed to process question');
    }
  };

  // ============================================================================
  // TEXT QUESTIONS
  // ============================================================================

  const askQuestion = async (question = null) => {
    const q = question || questionText.trim();
    
    if (!q) {
      Alert.alert('Empty Question', 'Please enter a question');
      return;
    }

    setIsProcessing(true);
    setAnswerData(null);

    try {
      const response = await fetch(`${API_URL}/ask`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${accessToken}`,
        },
        body: JSON.stringify({
          question: q,
          voice_response: true,
          voice_preference: VOICE_PREFERENCE, // Pleasant feminine voice
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to get answer');
      }

      const data = await response.json();
      setAnswerData(data);

      // Auto-play audio response with pleasant feminine voice
      if (data.answer_audio_url) {
        await playAudio(data.answer_audio_url);
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
      const { sound } = await Audio.Sound.createAsync({ 
        uri: `${API_URL}${url}` 
      });
      setPlayingSound(sound);
      await sound.playAsync();

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

  // ============================================================================
  // LOGS
  // ============================================================================

  const loadRecentLogs = async () => {
    try {
      const response = await fetch(`${API_URL}/logs?days=7`, {
        headers: {
          'Authorization': `Bearer ${accessToken}`,
        },
      });

      if (!response.ok) return;

      const logs = await response.json();
      setRecentLogs(logs);

    } catch (error) {
      console.error('Error loading logs:', error);
    }
  };

  // Quick question buttons
  const quickQuestions = [
    "Did I take my medication today?",
    "What did I eat yesterday?",
    "What activities did I do this week?",
    "When was my last doctor visit?",
  ];

  // ============================================================================
  // RENDER
  // ============================================================================

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
            Voice & text logging for tracking daily activities
          </Text>
        </View>
      </SafeAreaView>
    );
  }

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

        {/* Record Activity Section */}
        <View style={styles.recordSection}>
          <Text style={styles.sectionTitle}>Record Activity</Text>
          
          {/* Input Mode Toggle */}
          <View style={styles.modeToggle}>
            <TouchableOpacity
              style={[styles.modeButton, recordMode === 'voice' && styles.modeButtonActive]}
              onPress={() => setRecordMode('voice')}
            >
              <Text style={[styles.modeButtonText, recordMode === 'voice' && styles.modeButtonTextActive]}>
                🎤 Voice
              </Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.modeButton, recordMode === 'text' && styles.modeButtonActive]}
              onPress={() => setRecordMode('text')}
            >
              <Text style={[styles.modeButtonText, recordMode === 'text' && styles.modeButtonTextActive]}>
                ⌨️ Text
              </Text>
            </TouchableOpacity>
          </View>

          {recordMode === 'voice' ? (
            <>
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
                  {isRecording ? 'Tap to stop' : 'Tap to record activity'}
                </Text>
              </TouchableOpacity>
            </>
          ) : (
            <>
              <TextInput
                style={styles.textInput}
                multiline
                numberOfLines={6}
                placeholder="Type what you did today...&#10;&#10;Example: I went for a 30-minute walk and had breakfast."
                placeholderTextColor="#999"
                value={activityText}
                onChangeText={setActivityText}
              />
              <TouchableOpacity
                style={styles.submitButton}
                onPress={submitTextActivity}
                disabled={isProcessing}
              >
                <Text style={styles.submitButtonText}>📝 Save Activity</Text>
              </TouchableOpacity>
            </>
          )}

          {isProcessing && (
            <ActivityIndicator size="large" color="#007AFF" style={styles.spinner} />
          )}
        </View>

        {/* Ask Questions Section */}
        <View style={styles.questionsSection}>
          <Text style={styles.sectionTitle}>Ask Questions</Text>
          
          {/* Input Mode Toggle */}
          <View style={styles.modeToggle}>
            <TouchableOpacity
              style={[styles.modeButton, questionMode === 'text' && styles.modeButtonActive]}
              onPress={() => setQuestionMode('text')}
            >
              <Text style={[styles.modeButtonText, questionMode === 'text' && styles.modeButtonTextActive]}>
                ⌨️ Text
              </Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.modeButton, questionMode === 'voice' && styles.modeButtonActive]}
              onPress={() => setQuestionMode('voice')}
            >
              <Text style={[styles.modeButtonText, questionMode === 'voice' && styles.modeButtonTextActive]}>
                🎤 Voice
              </Text>
            </TouchableOpacity>
          </View>

          {questionMode === 'text' ? (
            <>
              <TextInput
                style={styles.questionInput}
                multiline
                numberOfLines={4}
                placeholder="What did I eat yesterday?"
                placeholderTextColor="#999"
                value={questionText}
                onChangeText={setQuestionText}
              />
              <TouchableOpacity
                style={styles.askButton}
                onPress={() => askQuestion()}
                disabled={isProcessing}
              >
                <Text style={styles.askButtonText}>✨ Ask AI</Text>
              </TouchableOpacity>
            </>
          ) : (
            <TouchableOpacity
              style={[
                styles.recordButton,
                styles.recordButtonSmall,
                isQuestionRecording && styles.recordButtonActive,
              ]}
              onPress={isQuestionRecording ? stopQuestionRecording : startQuestionRecording}
              disabled={isProcessing}
            >
              <Text style={styles.recordButtonText}>
                {isQuestionRecording ? '⏹️ STOP' : '🎤 ASK'}
              </Text>
              <Text style={styles.recordButtonSubtext}>
                {isQuestionRecording ? 'Tap to stop' : 'Tap to ask question'}
              </Text>
            </TouchableOpacity>
          )}

          {/* Answer Display */}
          {answerData && (
            <View style={styles.answerBox}>
              <Text style={styles.answerLabel}>AI Answer:</Text>
              <Text style={styles.answerText}>{answerData.answer_text}</Text>
              {answerData.answer_audio_url && (
                <Text style={styles.audioIndicator}>🔊 Playing pleasant feminine voice...</Text>
              )}
            </View>
          )}

          {/* Quick Questions */}
          <View style={styles.quickQuestions}>
            <Text style={styles.quickQuestionsTitle}>Quick Questions:</Text>
            {quickQuestions.map((q, index) => (
              <TouchableOpacity
                key={index}
                style={styles.quickQuestionButton}
                onPress={() => {
                  setQuestionText(q);
                  setQuestionMode('text');
                  askQuestion(q);
                }}
                disabled={isProcessing}
              >
                <Text style={styles.quickQuestionText}>{q}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>

        {/* Recent Logs */}
        <View style={styles.logsSection}>
          <Text style={styles.sectionTitle}>Recent Activities</Text>
          {recentLogs.length === 0 ? (
            <Text style={styles.noLogsText}>
              No activities yet. Start by recording!
            </Text>
          ) : (
            recentLogs.slice(0, 10).map((log) => (
              <View key={log.id} style={styles.logItem}>
                <View style={styles.logHeader}>
                  <Text style={styles.logTime}>
                    {new Date(log.timestamp).toLocaleDateString()} at{' '}
                    {new Date(log.timestamp).toLocaleTimeString()}
                  </Text>
                  <View style={[
                    styles.logBadge,
                    log.input_type === 'voice' ? styles.badgeVoice : styles.badgeText
                  ]}>
                    <Text style={styles.logBadgeText}>
                      {log.input_type === 'voice' ? '🎤 Voice' : '⌨️ Text'}
                    </Text>
                  </View>
                </View>
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
// STYLES
// ============================================================================

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#FFFFFF',
  },
  scrollView: {
    flex: 1,
  },
  
  // Sign-in
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
  
  // Header
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
  
  // Sections
  recordSection: {
    padding: 20,
  },
  questionsSection: {
    padding: 20,
    paddingTop: 0,
  },
  logsSection: {
    padding: 20,
    paddingTop: 0,
    paddingBottom: 40,
  },
  sectionTitle: {
    fontSize: 28,
    fontWeight: 'bold',
    color: '#000000',
    marginBottom: 15,
  },
  
  // Mode Toggle
  modeToggle: {
    flexDirection: 'row',
    backgroundColor: '#F5F5F5',
    borderRadius: 12,
    padding: 4,
    marginBottom: 20,
  },
  modeButton: {
    flex: 1,
    paddingVertical: 12,
    alignItems: 'center',
    borderRadius: 10,
  },
  modeButtonActive: {
    backgroundColor: '#FFFFFF',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
    elevation: 2,
  },
  modeButtonText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#999999',
  },
  modeButtonTextActive: {
    color: '#007AFF',
  },
  
  // Voice Recording
  recordButton: {
    width: 200,
    height: 200,
    borderRadius: 100,
    backgroundColor: '#FF3B30',
    justifyContent: 'center',
    alignItems: 'center',
    alignSelf: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 5,
    elevation: 8,
  },
  recordButtonSmall: {
    width: 150,
    height: 150,
    borderRadius: 75,
  },
  recordButtonActive: {
    backgroundColor: '#FF9500',
  },
  recordButtonText: {
    fontSize: 28,
    fontWeight: 'bold',
    color: '#FFFFFF',
    marginBottom: 5,
  },
  recordButtonSubtext: {
    fontSize: 14,
    color: '#FFFFFF',
    textAlign: 'center',
    paddingHorizontal: 20,
  },
  
  // Text Input
  textInput: {
    backgroundColor: '#F9F9F9',
    borderWidth: 2,
    borderColor: '#EEEEEE',
    borderRadius: 12,
    padding: 15,
    fontSize: 16,
    minHeight: 150,
    textAlignVertical: 'top',
    marginBottom: 15,
  },
  questionInput: {
    backgroundColor: '#F9F9F9',
    borderWidth: 2,
    borderColor: '#EEEEEE',
    borderRadius: 12,
    padding: 15,
    fontSize: 16,
    minHeight: 100,
    textAlignVertical: 'top',
    marginBottom: 15,
  },
  
  // Buttons
  submitButton: {
    backgroundColor: '#34C759',
    padding: 18,
    borderRadius: 12,
    alignItems: 'center',
  },
  submitButtonText: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#FFFFFF',
  },
  askButton: {
    backgroundColor: '#007AFF',
    padding: 18,
    borderRadius: 12,
    alignItems: 'center',
  },
  askButtonText: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#FFFFFF',
  },
  
  // Answer
  answerBox: {
    backgroundColor: '#F0F7FF',
    borderLeftWidth: 4,
    borderLeftColor: '#007AFF',
    padding: 15,
    borderRadius: 12,
    marginTop: 15,
  },
  answerLabel: {
    fontSize: 16,
    fontWeight: 'bold',
    color: '#007AFF',
    marginBottom: 8,
  },
  answerText: {
    fontSize: 16,
    lineHeight: 24,
    color: '#333333',
  },
  audioIndicator: {
    fontSize: 14,
    color: '#007AFF',
    marginTop: 10,
    fontStyle: 'italic',
  },
  
  // Quick Questions
  quickQuestions: {
    marginTop: 20,
  },
  quickQuestionsTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: '#666666',
    marginBottom: 10,
  },
  quickQuestionButton: {
    backgroundColor: '#F5F5F5',
    padding: 15,
    borderRadius: 12,
    marginBottom: 10,
  },
  quickQuestionText: {
    fontSize: 16,
    color: '#333333',
  },
  
  // Logs
  noLogsText: {
    fontSize: 18,
    color: '#999999',
    textAlign: 'center',
    padding: 30,
  },
  logItem: {
    backgroundColor: '#F9F9F9',
    padding: 15,
    borderRadius: 12,
    marginBottom: 12,
    borderLeftWidth: 4,
    borderLeftColor: '#007AFF',
  },
  logHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },
  logTime: {
    fontSize: 14,
    color: '#999999',
  },
  logBadge: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 12,
  },
  badgeVoice: {
    backgroundColor: '#E8F4FF',
  },
  badgeText: {
    backgroundColor: '#F0F0F0',
  },
  logBadgeText: {
    fontSize: 12,
    fontWeight: '600',
    color: '#666666',
  },
  logText: {
    fontSize: 16,
    color: '#333333',
    lineHeight: 22,
  },
  
  // Spinner
  spinner: {
    marginTop: 20,
  },
});

export default App;
