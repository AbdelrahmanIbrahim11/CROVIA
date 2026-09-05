import React, { useState } from 'react';
import { SafeAreaView, StatusBar, View } from 'react-native';
import { TabBar, TabKey } from './src/components/Chrome';
import { notifications } from './src/data';
import { AdminDashboardScreen } from './src/screens/AdminDashboardScreen';
import { NotificationsScreen } from './src/screens/NotificationsScreen';
import { PoliceDashboardScreen } from './src/screens/PoliceDashboardScreen';
import { ProfileScreen } from './src/screens/ProfileScreen';
import { Role, SignInScreen } from './src/screens/SignInScreen';
import { SignUpScreen } from './src/screens/SignUpScreen';
import { UserDashboardScreen } from './src/screens/UserDashboardScreen';
import { ThemeProvider, useTheme } from './src/theme/ThemeProvider';

/**
 * Deliberately minimal navigation so the design can be reviewed end to end
 * without pulling in react-navigation. Replace with a real navigator when
 * the app gets its logic.
 */

type Route = 'signin' | 'signup' | 'citizen' | 'admin' | 'police';

function Shell() {
  const { colors, scheme } = useTheme();
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
  } else if (route === 'admin') {
    body = <AdminDashboardScreen onSignOut={() => setRoute('signin')} />;
  } else if (route === 'police') {
    body = <PoliceDashboardScreen onSignOut={() => setRoute('signin')} />;
  } else {
    body = (
      <View style={{ flex: 1 }}>
        <View style={{ flex: 1 }}>
          {tab === 'map' ? (
            <UserDashboardScreen
              unread={unread}
              onOpenAlerts={() => setTab('alerts')}
              onSignOut={() => setRoute('signin')}
            />
          ) : tab === 'alerts' ? (
            <NotificationsScreen />
          ) : (
            <ProfileScreen onSignOut={() => setRoute('signin')} />
          )}
        </View>
        <TabBar active={tab} unread={unread} onChange={setTab} />
      </View>
    );
  }

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.bgBase }}>
      <StatusBar barStyle={scheme === 'dark' ? 'light-content' : 'dark-content'} />
      {body}
    </SafeAreaView>
  );
}

export default function App() {
  return (
    <ThemeProvider>
      <Shell />
    </ThemeProvider>
  );
}
