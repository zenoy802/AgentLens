import createClient from "openapi-fetch";

import type { paths } from "./types.gen";

export const apiClient = createClient<paths>({ baseUrl: "/api/v1" });
