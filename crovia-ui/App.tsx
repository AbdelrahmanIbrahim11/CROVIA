import React, { useEffect, useState } from 'react';
import { SafeAreaView, StatusBar, View } from 'react-native';
import { GluestackUIProvider } from '@gluestack-ui/themed';
import { config } from '@gluestack-ui/config';
import { TabBar, TabKey } from './src/components/Chrome';
import { notifications } from './src/data';
import { AdminDashboardScreen } from './src/screens/AdminDashboardScreen';
import { NotificationsScreen } from './src/screens/NotificationsScreen';
import { PoliceDashboardScreen } from './src/screens/PoliceDashboardScreen';
import { ProfileScreen } from './src/screens/ProfileScreen';
import { SignInScreen } from './src/screens/SignInScreen';
import { SignUpScreen } from './src/screens/SignUpScreen';
import { UserDashboardScreen } from './src/screens/UserDashboardScreen';
import { ThemeProvider } from './src/theme/ThemeProvider';
import {
  Session,
  clearSession,
  loadSession,
  signOut as apiSignOut,
  stillValid,
} from './src/session';

type Route = 'signin' | 'signup' | 'citizen' | 'admin' | 'police';

/** Which screen an account type lands on. The backend decides the role, not the app. */
const HOME: Record<Session['role'], Route> = {
  normal: 'citizen',
  admin: 'admin',
  authority: 'police',
};

function Shell() {
  // Start from whatever is stored, so a reload does not sign the person out.
  const [session, setSession] = useState<Session | null>(() => loadSession());
  const [route, setRoute] = useState<Route>(() => {
    const s = loadSession();
    return s ? HOME[s.role] : 'signin';
  });
  const [tab, setTab] = useState<TabKey>('map');

  // A stored token can be expired or signed with a key the server no longer
  // has. Checking once at start means the person is sent to the sign-in screen
  // instead of staring at a dashboard where nothing loads.
  useEffect(() => {
    if (!session) return;
    let cancelled = false;
    stillValid().then((ok) => {
      if (!ok && !cancelled) {
        clearSession();
        setSession(null);
        setRoute('signin');
      }
    });
    return () => {
      cancelled = true;
    };
    // Runs once per signed-in session, not on every render.
  }, [session?.token]);

  const unread = 0; // Removed hardcoded demo notifications

  const handleSignIn = (s: Session) => {
    setSession(s);
    setTab('map');
    setRoute(HOME[s.role]);
  };

  const handleSignOut = async () => {
    await apiSignOut();
    setSession(null);
    setRoute('signin');
  };

  let body: React.ReactNode = null;

  // Sign-up is checked first. Nobody has a session while creating an account,
  // so testing for "no session" before this sent them straight back to sign-in
  // and the sign-up screen could never open.
  if (route === 'signup') {
    body = <SignUpScreen onCreate={() => setRoute('signin')} onBack={() => setRoute('signin')} />;
  } else if (route === 'signin' || !session) {
    body = <SignInScreen onSignIn={handleSignIn} onSignUp={() => setRoute('signup')} />;
  } else {
    // All authenticated routes now have the Tab Bar!
    let activeScreen: React.ReactNode = null;

    if (tab === 'alerts') {
      activeScreen = <NotificationsScreen />;
    } else if (tab === 'profile') {
      activeScreen = <ProfileScreen onSignOut={handleSignOut} />;
    } else {
      // tab is 'map'
      if (route === 'admin') {
        activeScreen = <AdminDashboardScreen onSignOut={handleSignOut} />;
      } else if (route === 'police') {
        activeScreen = <PoliceDashboardScreen onSignOut={handleSignOut} />;
      } else {
        activeScreen = (
          <UserDashboardScreen
            unread={unread}
            onOpenAlerts={() => setTab('alerts')}
            onSignOut={handleSignOut}
          />
        );
      }
    }

    body = (
      <View style={{ flex: 1 }}>
        <View style={{ flex: 1 }}>
          {activeScreen}
        </View>
        <TabBar active={tab} unread={unread} onChange={setTab} />
      </View>
    );
  }

  // We enforce the deep navy color everywhere to match the auth screens
  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: '#161A28' }}>
      <StatusBar barStyle="light-content" />
      {body}
    </SafeAreaView>
  );
}

export default function App() {
  return (
    <ThemeProvider>
      <GluestackUIProvider config={config}>
        <Shell />
      </GluestackUIProvider>
    </ThemeProvider>
  );
}
