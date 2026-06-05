import {
  darkTheme as naiveDarkTheme,
  lightTheme as naiveLightTheme,
  type GlobalThemeOverrides,
} from 'naive-ui'

/** Единое скругление полей ввода, селектов и кнопок. */
const CONTROL_RADIUS = '8px'

const sharedOverrides: GlobalThemeOverrides = {
  common: {
    borderRadius: CONTROL_RADIUS,
    borderRadiusSmall: CONTROL_RADIUS,
    fontFamily:
      'system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
  },
  Input: {
    borderRadius: CONTROL_RADIUS,
  },
  Select: {
    peers: {
      InternalSelection: {
        borderRadius: CONTROL_RADIUS,
      },
    },
  },
  InternalSelection: {
    borderRadius: CONTROL_RADIUS,
  },
  Button: {
    borderRadiusTiny: CONTROL_RADIUS,
    borderRadiusSmall: CONTROL_RADIUS,
    borderRadiusMedium: CONTROL_RADIUS,
    borderRadiusLarge: CONTROL_RADIUS,
  },
  Tag: {
    borderRadius: CONTROL_RADIUS,
  },
  Card: {
    borderRadius: CONTROL_RADIUS,
  },
  Dialog: {
    borderRadius: CONTROL_RADIUS,
  },
  Popover: {
    borderRadius: CONTROL_RADIUS,
  },
  Tabs: {
    tabBorderRadius: CONTROL_RADIUS,
  },
}

export const lightTheme = naiveLightTheme
export const darkTheme = naiveDarkTheme

export const lightThemeOverrides: GlobalThemeOverrides = {
  ...sharedOverrides,
  common: {
    ...sharedOverrides.common,
    bodyColor: '#f5f6f8',
    cardColor: '#ffffff',
  },
}

export const darkThemeOverrides: GlobalThemeOverrides = {
  ...sharedOverrides,
  common: {
    ...sharedOverrides.common,
    bodyColor: '#0f1117',
    cardColor: '#161b22',
  },
  Input: {
    ...sharedOverrides.Input,
    color: '#21262d',
    colorDisabled: '#161b22',
    colorFocus: '#21262d',
    textColor: '#e6edf3',
    placeholderColor: '#8b949e',
    border: '1px solid #30363d',
    borderHover: '1px solid #58a6ff',
    borderFocus: '1px solid #58a6ff',
  },
}
