import Ionicons from '@expo/vector-icons/Ionicons';
import { Tabs } from 'expo-router/js-tabs';
import type { ComponentProps } from 'react';
import type { ColorValue } from 'react-native';

import { colors } from '@/components/theme';

type IconName = ComponentProps<typeof Ionicons>['name'];

/**
 * JS tabs ship with Expo Router. The icons are an icon font loaded through expo-font, which
 * the development build already contains (ADR 0014), so neither needs a new build.
 */
function icon(selected: IconName, unselected: IconName) {
  function TabIcon({
    focused,
    color,
    size,
  }: {
    focused: boolean;
    color: ColorValue;
    size: number;
  }) {
    return <Ionicons name={focused ? selected : unselected} color={color as string} size={size} />;
  }
  return TabIcon;
}

export default function TabsLayout() {
  return (
    <Tabs screenOptions={{ tabBarActiveTintColor: colors.accent }}>
      <Tabs.Screen
        name="index"
        options={{
          title: 'NextPay',
          tabBarLabel: 'Home',
          tabBarIcon: icon('home', 'home-outline'),
        }}
      />
      <Tabs.Screen
        name="setup"
        options={{
          title: 'Setup',
          headerShown: false,
          tabBarIcon: icon('options', 'options-outline'),
        }}
      />
    </Tabs>
  );
}
