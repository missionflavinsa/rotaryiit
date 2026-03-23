// Firebase Client SDK Configuration
import 'react-native-url-polyfill/auto';
import { initializeApp } from 'firebase/app';
import { initializeAuth, getReactNativePersistence } from 'firebase/auth';
import { getFirestore } from 'firebase/firestore';
import AsyncStorage from '@react-native-async-storage/async-storage';

const firebaseConfig = {
  apiKey: "AIzaSyB73ZFrSWpXH58V9YoC5fVAfa_w8nYBvkE",
  authDomain: "rotary-iit.firebaseapp.com",
  projectId: "rotary-iit",
  storageBucket: "rotary-iit.firebasestorage.app",
  messagingSenderId: "438254376229",
  appId: "1:438254376229:web:c18f58aed17feffc21b6cc"
};

const app = initializeApp(firebaseConfig);
export const auth = initializeAuth(app, {
  persistence: getReactNativePersistence(AsyncStorage)
});
export const db = getFirestore(app);
