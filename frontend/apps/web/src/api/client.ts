import createClient from "openapi-fetch";

import type { paths } from "./types.gen";

export const API_BASE_URL = "/api/v1";

export const apiClient = createClient<paths>({ baseUrl: API_BASE_URL });
