// Firebase Client SDK Configuration
// Get these values from: Firebase Console -> Project Settings -> General -> Your Apps -> Web App
// If no web app exists, click "Add App" -> Web icon

import { initializeApp } from 'firebase/app';
import { getAuth } from 'firebase/auth';
import { getFirestore } from 'firebase/firestore';

const firebaseConfig = {
  apiKey: "AIzaSyB73ZFrSWpXH58V9YoC5fVAfa_w8nYBvkE",                    // Replace with your Firebase API key
  authDomain: "rotary-iit.firebaseapp.com",
  projectId: "rotary-iit",
  storageBucket: "rotary-iit.firebasestorage.app",
  messagingSenderId: "438254376229",       // Replace with your sender ID
  appId: "1:438254376229:web:c18f58aed17feffc21b6cc"                       // Replace with your app ID
};

const app = initializeApp(firebaseConfig);
export const auth = getAuth(app);
export const db = getFirestore(app);
