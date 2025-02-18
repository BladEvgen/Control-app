import { useState, useRef } from "react";

const useWaitNotification = () => {
  const [showWaitMessage, setShowWaitMessage] = useState(false);
  const downloadTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const waitMessageTimerRef = useRef<NodeJS.Timeout | null>(null);

  const startWaitNotification = () => {
    clearWaitNotification();
    downloadTimeoutRef.current = setTimeout(() => {
      setShowWaitMessage(true);
      waitMessageTimerRef.current = setTimeout(() => {
        setShowWaitMessage(false);
      }, 7000);
    }, 3000);
  };

  const clearWaitNotification = () => {
    if (downloadTimeoutRef.current) {
      clearTimeout(downloadTimeoutRef.current);
      downloadTimeoutRef.current = null;
    }
    if (waitMessageTimerRef.current) {
      clearTimeout(waitMessageTimerRef.current);
      waitMessageTimerRef.current = null;
    }
    setShowWaitMessage(false);
  };

  return { showWaitMessage, startWaitNotification, clearWaitNotification };
};

export default useWaitNotification;
