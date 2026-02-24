import { createSlice, PayloadAction } from "@reduxjs/toolkit";

interface Notification {
  id: string;
  message: string;
  type: "success" | "error" | "warning" | "info";
  duration?: number;
}

interface UIState {
  notifications: Notification[];
  globalLoading: boolean;
  sidebarOpen: boolean;
  reportsAutoRefreshMinutes: number;
}

const initialState: UIState = {
  notifications: [],
  globalLoading: false,
  sidebarOpen: true,
  reportsAutoRefreshMinutes: 5,
};

const uiSlice = createSlice({
  name: "ui",
  initialState,
  reducers: {
    addNotification: (state, action: PayloadAction<Omit<Notification, "id">>) => {
      const id = `notification-${Date.now()}-${Math.random()}`;
      state.notifications.push({
        ...action.payload,
        id,
        duration: action.payload.duration || 5000,
      });
    },
    removeNotification: (state, action: PayloadAction<string>) => {
      state.notifications = state.notifications.filter(
        (notification) => notification.id !== action.payload
      );
    },
    clearNotifications: (state) => {
      state.notifications = [];
    },
    setGlobalLoading: (state, action: PayloadAction<boolean>) => {
      state.globalLoading = action.payload;
    },
    setSidebarOpen: (state, action: PayloadAction<boolean>) => {
      state.sidebarOpen = action.payload;
    },
    toggleSidebar: (state) => {
      state.sidebarOpen = !state.sidebarOpen;
    },
    setReportsAutoRefreshMinutes: (state, action: PayloadAction<number>) => {
      state.reportsAutoRefreshMinutes = Math.max(0, action.payload);
    },
  },
});

export const {
  addNotification,
  removeNotification,
  clearNotifications,
  setGlobalLoading,
  setSidebarOpen,
  toggleSidebar,
  setReportsAutoRefreshMinutes,
} = uiSlice.actions;

export default uiSlice.reducer;

