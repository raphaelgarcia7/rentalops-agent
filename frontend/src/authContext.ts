import { createContext } from 'react';

export const AuthContext = createContext<{ logout: () => void; busy: boolean }>(
  {
    logout: () => {},
    busy: false,
  },
);
