import { city } from './geo';

/**
 * The city's name, and nothing else.
 *
 * This file used to hold a complete invented evening: markers, density blobs,
 * crowd clusters, a list of notifications and a table of zone rows, all with
 * confident-looking figures - "~2,400 people, extrapolated from 18 fixes",
 * "89k people leaving at once". Every screen has since been rewired to live
 * data, and none of it was imported any more.
 *
 * It is deleted rather than left lying about because invented crowd numbers in
 * a crowd-safety codebase are not harmless. One careless import puts a
 * fabricated headcount on a map that people are meant to act on, and it would
 * look exactly like a real one.
 */
export const REGION = city.label;
export const REGION_SUB = city.sublabel;
