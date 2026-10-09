// Non-secret configuration generated from the Python source of truth by
// src/dashboard/build.py (service catalog, follow-up delays). No lead data.
import generated from '../generated/app-config.json';

export interface AppConfig {
  services: Array<Record<string, any>>;
  followUpDelays: Record<string, number>;
}

export const appConfig: AppConfig = generated as AppConfig;
