import { useCallback, useEffect, useState } from 'react';
import { tokenStorage } from '../api/client';

const SUBSCRIBERS = new Set<(value: string) => void>();

const broadcast = (value: string) => {
  for (const fn of SUBSCRIBERS) fn(value);
};

export function useToken(): {
  token: string;
  setToken: (value: string) => void;
  hasToken: boolean;
} {
  const [token, setTokenState] = useState<string>(() => tokenStorage.get());

  useEffect(() => {
    SUBSCRIBERS.add(setTokenState);
    return () => {
      SUBSCRIBERS.delete(setTokenState);
    };
  }, []);

  const setToken = useCallback((value: string) => {
    tokenStorage.set(value);
    broadcast(value);
  }, []);

  return { token, setToken, hasToken: !!token };
}
