/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Endereço público do serviço `auth` (login) do backend, sem barra no fim. */
  readonly VITE_AUTH_BASE_URL?: string;
  /** Endereço público do serviço `backend` (API), sem barra no fim. */
  readonly VITE_API_BASE_URL?: string;
}
