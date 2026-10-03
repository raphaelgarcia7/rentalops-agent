import { createContext } from 'react';

export const AuthContext = createContext<{
  logout: () => void;
  busy: boolean;
  authenticated: boolean;
}>({
  logout: () => {},
  busy: false,
  authenticated: true,
});
