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

export function useRealtimeUpdates(onUpdate) {
  const [isConnected, setIsConnected] = useState(false);
  const [lastUpdate, setLastUpdate] = useState(null);
  const eventSourceRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);
  const reconnectAttempts = useRef(0);

  const connect = useCallback(() => {
    // Clean up existing connection
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }

    const url = `${BACKEND_URL}/api/updates/stream`;
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
      console.error('[SSE] Connection error:', error);
      setIsConnected(false);
      eventSource.close();

      // Exponential backoff for reconnection
      const delay = Math.min(1000 * Math.pow(2, reconnectAttempts.current), 30000);
      reconnectAttempts.current += 1;

      console.log(`[SSE] Reconnecting in ${delay}ms (attempt ${reconnectAttempts.current})`);
      
      reconnectTimeoutRef.current = setTimeout(() => {
        connect();
      }, delay);
    };

    eventSourceRef.current = eventSource;
  }, [onUpdate]);

  useEffect(() => {
    connect();

    // Cleanup on unmount
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
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
