/**
 * VeriDictum AI — Global ErrorBoundary
 *
 * Catches render-time errors anywhere below it and shows a recovery surface
 * instead of the white screen of death. Class component because React's
 * error-boundary API still requires componentDidCatch / getDerivedStateFromError.
 */

import { Component, type ErrorInfo, type ReactNode } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Surface to the console with the React component stack so the developer
    // tools "show source" jump works. In production we'd ship this to Sentry
    // or similar; for the demo a console.error is the right thing.
    console.error("[ErrorBoundary]", error, info.componentStack);
  }

  private handleReload = (): void => {
    this.setState({ error: null });
    window.location.reload();
  };

  render(): ReactNode {
    if (!this.state.error) return this.props.children;

    return (
      <div className="min-h-screen flex items-center justify-center bg-navy-900 px-6">
        <div className="max-w-md w-full bg-white rounded-2xl shadow-2xl p-8 text-center">
          <div className="w-14 h-14 rounded-full bg-red-50 flex items-center justify-center mx-auto mb-5">
            <AlertTriangle className="w-7 h-7 text-red-600" aria-hidden="true" />
          </div>
          <h1 className="text-xl font-semibold text-gray-900 mb-2">
            Something went wrong
          </h1>
          <p className="text-sm text-gray-600 mb-5">
            Sarvam Nyaya hit an unexpected error and could not render this view.
            The error has been logged. Reloading usually clears the problem.
          </p>
          {import.meta.env.DEV && (
            <pre className="text-left text-[11px] bg-gray-50 rounded p-3 mb-5 overflow-auto max-h-48 text-red-700">
              {this.state.error.stack ?? this.state.error.message}
            </pre>
          )}
          <button
            onClick={this.handleReload}
            className="inline-flex items-center gap-2 px-5 py-2.5 bg-navy-600 text-white rounded-lg font-medium hover:bg-navy-700 transition-colors"
          >
            <RefreshCw className="w-4 h-4" aria-hidden="true" />
            Reload the page
          </button>
        </div>
      </div>
    );
  }
}
