import { useCallback, useEffect, useState } from "react";

import {
  getTelemetryPreferences,
  updateTelemetryPreferences,
  type TelemetryPreferences
} from "../api/telemetry";

export interface ErrorReportingState {
  loading: boolean;
  preferences: TelemetryPreferences | null;
  showConsentPrompt: boolean;
  reload: () => Promise<void>;
  acceptConsent: () => Promise<void>;
  declineConsent: () => Promise<void>;
  setErrorReportingEnabled: (enabled: boolean) => Promise<void>;
}

export function useErrorReporting(backendReady: boolean): ErrorReportingState {
  const [loading, setLoading] = useState(false);
  const [preferences, setPreferences] = useState<TelemetryPreferences | null>(null);

  const reload = useCallback(async () => {
    if (!backendReady) {
      setPreferences(null);
      return;
    }
    setLoading(true);
    try {
      setPreferences(await getTelemetryPreferences());
    } catch {
      setPreferences(null);
    } finally {
      setLoading(false);
    }
  }, [backendReady]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const recordChoice = useCallback(
    async (enableReporting: boolean) => {
      const updated = await updateTelemetryPreferences({
        telemetry_enabled: enableReporting,
        crash_reporting_enabled: enableReporting,
        record_consent_prompt_shown: true,
        updated_by: "atlas-desktop"
      });
      setPreferences(updated);
    },
    []
  );

  const acceptConsent = useCallback(async () => {
    await recordChoice(true);
  }, [recordChoice]);

  const declineConsent = useCallback(async () => {
    await recordChoice(false);
  }, [recordChoice]);

  const setErrorReportingEnabled = useCallback(async (enabled: boolean) => {
    const updated = await updateTelemetryPreferences({
      telemetry_enabled: enabled,
      crash_reporting_enabled: enabled,
      updated_by: "atlas-desktop"
    });
    setPreferences(updated);
  }, []);

  const showConsentPrompt =
    !loading &&
    preferences?.error_reporting_available === true &&
    preferences.consent_prompt_pending === true;

  return {
    loading,
    preferences,
    showConsentPrompt,
    reload,
    acceptConsent,
    declineConsent,
    setErrorReportingEnabled
  };
}
