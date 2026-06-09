/**
 * useRealtimeUpdates - React hook for Server-Sent Events (SSE) connection
 * 
 * Automatically reconnects on disconnect and provides real-time updates for:
 * - Predictions
 * - Corrections
 * - Captures
 */
import { useEffect, useRef, useState, useCallback } from 'react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
const CAPABILITY_PATH = '/api/meta';
const STREAM_PATH = '/api/updates/stream';
const MAX_RECONNECT_ATTEMPTS = 5;

export function useRealtimeUpdates(onUpdate) {
  const [isConnected, setIsConnected] = useState(false);
  const [lastUpdate, setLastUpdate] = useState(null);
  const eventSourceRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);
  const preflightAbortRef = useRef(null);
  const reconnectAttempts = useRef(0);
  const capabilityCheckedRef = useRef(false);
  const realtimeSupportedRef = useRef(false);

  const checkRealtimeSupport = useCallback(async () => {
    if (capabilityCheckedRef.current) {
      return realtimeSupportedRef.current;
    }

    try {
      const controller = new AbortController();
      preflightAbortRef.current = controller;
      const timeoutId = setTimeout(() => controller.abort(), 5000);
      const response = await fetch(`${BACKEND_URL}${CAPABILITY_PATH}`, {
        headers: { Accept: 'application/json' },
        signal: controller.signal,
      });
      clearTimeout(timeoutId);
      preflightAbortRef.current = null;

      if (!response.ok) {
        return false;
      }

      const data = await response.json();
      realtimeSupportedRef.current = data?.features?.realtime_updates === true;
      capabilityCheckedRef.current = true;

      if (!realtimeSupportedRef.current) {
        console.info('[SSE] Real-time update endpoint is not advertised by the API; live updates disabled for this session.');
      }

      return realtimeSupportedRef.current;
    } catch (error) {
      preflightAbortRef.current = null;
      if (error.name !== 'AbortError') {
        console.warn('[SSE] Feature check failed; live updates disabled for this session:', error);
      }
      return false;
    }
  }, []);

  const connect = useCallback(async () => {
    if (!(await checkRealtimeSupport())) {
      return;
    }

    // Clean up existing connection
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }

    const url = `${BACKEND_URL}${STREAM_PATH}`;
    const eventSource = new EventSource(url);

    eventSource.onopen = () => {
      console.log('[SSE] Connected to real-time updates');
      setIsConnected(true);
      reconnectAttempts.current = 0;
    };

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        console.log('[SSE] Received update:', data);
        
        setLastUpdate({
          ...data,
          timestamp: new Date().toISOString(),
        });

        // Call the callback if provided
        if (onUpdate && typeof onUpdate === 'function') {
          onUpdate(data);
        }
      } catch (err) {
        console.error('[SSE] Failed to parse event data:', err);
      }
    };

    eventSource.onerror = (error) => {
      console.warn('[SSE] Connection error:', error);
      setIsConnected(false);
      eventSource.close();

      if (reconnectAttempts.current >= MAX_RECONNECT_ATTEMPTS) {
        console.info('[SSE] Real-time reconnect limit reached; live updates disabled for this session.');
        return;
      }

      // Exponential backoff for reconnection
      const delay = Math.min(1000 * Math.pow(2, reconnectAttempts.current), 30000);
      reconnectAttempts.current += 1;

      console.log(`[SSE] Reconnecting in ${delay}ms (attempt ${reconnectAttempts.current})`);
      
      reconnectTimeoutRef.current = setTimeout(() => {
        connect();
      }, delay);
    };

    eventSourceRef.current = eventSource;
  }, [checkRealtimeSupport, onUpdate]);

  useEffect(() => {
    connect();

    // Cleanup on unmount
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
      if (preflightAbortRef.current) {
        preflightAbortRef.current.abort();
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
    };
  }, [connect]);

  return {
    isConnected,
    lastUpdate,
  };
}
