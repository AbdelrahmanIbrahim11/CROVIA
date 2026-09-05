import React, { useState } from 'react';
import { SafeAreaView, StatusBar, View } from 'react-native';
import { GluestackUIProvider } from '@gluestack-ui/themed';
import { config } from '@gluestack-ui/config';
import { TabBar, TabKey } from './src/components/Chrome';
import { notifications } from './src/data';
import { AdminDashboardScreen } from './src/screens/AdminDashboardScreen';
import { NotificationsScreen } from './src/screens/NotificationsScreen';
import { PoliceDashboardScreen } from './src/screens/PoliceDashboardScreen';
import { ProfileScreen } from './src/screens/ProfileScreen';
import { Role, SignInScreen } from './src/screens/SignInScreen';
import { SignUpScreen } from './src/screens/SignUpScreen';
import { UserDashboardScreen } from './src/screens/UserDashboardScreen';
import { ThemeProvider } from './src/theme/ThemeProvider';

type Route = 'signin' | 'signup' | 'citizen' | 'admin' | 'police';

function Shell() {
  const [route, setRoute] = useState<Route>('signin');
  const [tab, setTab] = useState<TabKey>('map');

  const unread = notifications.filter((n) => n.unread).length;

  const signIn = (role: Role) => {
    setTab('map');
    setRoute(role === 'citizen' ? 'citizen' : role === 'admin' ? 'admin' : 'police');
  };

  let body: React.ReactNode = null;

  if (route === 'signin') {
    body = <SignInScreen onSignIn={signIn} onSignUp={() => setRoute('signup')} />;
  } else if (route === 'signup') {
    body = <SignUpScreen onCreate={() => setRoute('citizen')} onBack={() => setRoute('signin')} />;
  } else {
    // All authenticated routes now have the Tab Bar!
    let activeScreen: React.ReactNode = null;

    if (tab === 'alerts') {
      activeScreen = <NotificationsScreen />;
    } else if (tab === 'profile') {
      activeScreen = <ProfileScreen onSignOut={() => setRoute('signin')} />;
    } else {
      // tab is 'map'
      if (route === 'admin') {
        activeScreen = <AdminDashboardScreen onSignOut={() => setRoute('signin')} />;
      } else if (route === 'police') {
        activeScreen = <PoliceDashboardScreen onSignOut={() => setRoute('signin')} />;
      } else {
        activeScreen = (
          <UserDashboardScreen
            unread={unread}
            onOpenAlerts={() => setTab('alerts')}
            onSignOut={() => setRoute('signin')}
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
