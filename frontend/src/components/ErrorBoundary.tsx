import { Component, ErrorInfo, ReactNode } from "react";
import { FaExclamationTriangle, FaHome, FaRedo } from "react-icons/fa";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error?: Error;
}

class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    console.error("ErrorBoundary caught:", error, errorInfo);
  }

  render(): ReactNode {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }
      return (
        <div className="flex flex-col justify-center items-center min-h-[60vh] px-4 py-12">
          <div className="card max-w-lg w-full p-8 animate-fadeInUp">
            <div className="flex flex-col items-center text-center">
              <div className="mb-6 p-4 rounded-full bg-danger-100 dark:bg-danger-700/20">
                <FaExclamationTriangle className="w-16 h-16 text-danger-600 dark:text-danger-400" />
              </div>
              <h2 className="text-2xl md:text-3xl font-bold bg-gradient-to-r from-primary-600 to-secondary-600 bg-clip-text text-transparent dark:from-primary-400 dark:to-secondary-400 mb-3">
                Ошибка загрузки
              </h2>
              <p className="text-gray-600 dark:text-gray-400 mb-8 leading-relaxed">
                Приложение не удалось загрузить. Попробуйте обновить страницу или
                использовать другой браузер.
              </p>
              <div className="flex flex-col sm:flex-row gap-4 w-full sm:w-auto">
                <button
                  type="button"
                  onClick={() => window.location.reload()}
                  className="btn-primary flex items-center justify-center gap-2"
                >
                  <FaRedo className="w-4 h-4" />
                  Обновить страницу
                </button>
                <a
                  href="/app"
                  className="btn bg-gray-200 dark:bg-gray-700 text-gray-800 dark:text-gray-200 hover:bg-gray-300 dark:hover:bg-gray-600 flex items-center justify-center gap-2"
                >
                  <FaHome className="w-4 h-4" />
                  На главную
                </a>
              </div>
            </div>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

export default ErrorBoundary;
