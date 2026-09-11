/**
 * Making the phone buzz when a crowd is dangerous.
 *
 * A warning that only appears when the app is already open is not a warning.
 * This asks the phone's operating system for a delivery address and gives it
 * to the backend, so an alarm arrives on a locked screen.
 *
 * Two things are worth knowing before reading further.
 *
 * A BROWSER CANNOT DO THIS. Push tokens are issued by iOS and Android to an
 * installed app. On web every function here returns quietly and the Alerts tab
 * remains the only delivery. That is why nothing appears to change until the
 * app is built and installed on a real phone.
 *
 * PERMISSION IS ASKED ONCE, AND LATE. Not on first launch, when a person has
 * no idea what the app does and says no out of habit, but after they have
 * signed up and agreed to be monitored - the moment the warning is obviously
 * the thing they just asked for.
 */

import { Platform } from 'react-native';
import * as Device from 'expo-device';
import * as Notifications from 'expo-notifications';
import { API_BASE } from './api';
import { authHeader } from './session';

/** Show the warning even while the app is open and in front of the person. */
Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowBanner: true,
    shouldShowList: true,
    shouldPlaySound: true,
    shouldSetBadge: true,
  }),
});

const isWeb = Platform.OS === 'web';

/**
 * Ask for permission, get the address, and give it to the backend.
 *
 * Returns the token, or null when there is nothing to register - on the web,
 * on a simulator, or when the person said no. A refusal is a normal outcome,
 * not an error: they keep the app and the Alerts tab, they just do not get
 * interrupted.
 */
export async function registerForPush(): Promise<string | null> {
  if (isWeb) return null;

  // A simulator has no push service behind it, so asking produces an error
  // rather than a token.
  if (!Device.isDevice) return null;

  try {
    const existing = await Notifications.getPermissionsAsync();
    let granted = existing.granted;

    if (!granted && existing.canAskAgain) {
      const asked = await Notifications.requestPermissionsAsync();
      granted = asked.granted;
    }
    if (!granted) return null;

    // Android shows notifications silently unless a channel exists, and a
    // crowd warning that arrives without a sound is a crowd warning nobody
    // notices.
    if (Platform.OS === 'android') {
      await Notifications.setNotificationChannelAsync('crowd-warnings', {
        name: 'Crowd warnings',
        importance: Notifications.AndroidImportance.MAX,
        vibrationPattern: [0, 250, 250, 250],
        sound: 'default',
      });
    }

    const projectId =
      // Set by EAS when the app is built. Without it Expo cannot issue a token.
      (Notifications as unknown as { easConfig?: { projectId?: string } })?.easConfig
        ?.projectId;
    const { data: token } = await Notifications.getExpoPushTokenAsync(
      projectId ? { projectId } : undefined,
    );

    await fetch(`${API_BASE}/api/push/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeader() },
      body: JSON.stringify({ token, platform: Platform.OS }),
    });

    return token;
  } catch {
    // Never let this break sign-in. The person is still warned in the app.
    return null;
  }
}

/** Forget this device, when someone signs out. */
export async function unregisterPush(token: string | null): Promise<void> {
  if (!token || isWeb) return;
  try {
    await fetch(`${API_BASE}/api/push/register`, {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json', ...authHeader() },
      body: JSON.stringify({ token }),
    });
  } catch {
    // Signing out locally is what matters; the token expires on its own.
  }
}

/**
 * Run `onOpenWarning` when someone taps a notification.
 *
 * A person who taps a crowd warning wants to know what to do about it, so the
 * app opens the alarm rather than the map.
 */
export function onNotificationTap(
  onOpenWarning: (zoneId: string | null) => void,
): () => void {
  if (isWeb) return () => {};
  const sub = Notifications.addNotificationResponseReceivedListener((response) => {
    const data = response.notification.request.content.data as { zone_id?: string };
    onOpenWarning(data?.zone_id ?? null);
  });
  return () => sub.remove();
}
