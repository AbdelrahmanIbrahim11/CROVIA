import React from 'react';
import { View, StyleSheet } from 'react-native';
import {
  AttributionControl,
  MapLibreMap,
  NavigationControl,
  setWorkerUrl,
  type AddLayerObject,
  type GeoJSONSource,
  type MapMouseEvent,
} from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import circle from '@turf/circle';
import { useTheme } from '../theme/ThemeProvider';
import { city, districtById, zoneById, type LatLon } from '../geo';
import { ATTRIBUTION, basemapStyleUrl, severityColor } from '../geo/basemap';
import { MapMarker } from './MapMarker';
import type { CityMapProps, CrowdCluster, DensityBlob } from './CityMap.types';

export * from './CityMap.types';

/**
 * The real map surface: MapLibre over OpenStreetMap vector tiles.
 *
 * Everything geographic lives in MapLibre sources so it scales correctly with
 * zoom — a 500 m geofence has to *look* like 500 m of ground, because half the
 * argument of this product is that these circles are bigger than people assume.
 * Circles are geodesic polygons from turf rather than screen-space discs, which
 * is why they stay honest as you pan north.
 *
 * Pins are the exception. Those stay as React Native <MapMarker> views
 * positioned from `map.project()` on every camera move, so the marker styling
 * stays shared with the native implementation instead of forking into DOM.
 */

/**
 * Metro does not emit MapLibre's worker chunk, so point it at the copy that
 * `scripts/sync-maplibre-worker.mjs` places in `public/`. Without this the tile
 * worker 404s and you get a blank canvas with no useful error.
 */
setWorkerUrl('/maplibre-gl-worker.mjs');

const SRC = {
  districts: 'crovia-districts',
  zones: 'crovia-zones',
  blobs: 'crovia-blobs',
  clusterAccuracy: 'crovia-cluster-accuracy',
  clusterSpread: 'crovia-cluster-spread',
} as const;

function ring(center: LatLon, radiusM: number, props: Record<string, unknown>) {
  return circle([center.lon, center.lat], radiusM, {
    steps: 64,
    units: 'meters',
    properties: props,
  });
}

function districtFeatures(overlays: CityMapProps['districts']) {
  return {
    type: 'FeatureCollection' as const,
    features: (overlays ?? []).flatMap((o) => {
      const d = districtById[o.id];
      if (!d) return [];
      return [
        ring(d.center, d.radius_m, {
          id: d.id,
          label: d.label,
          short: d.short,
          color: severityColor(o.level),
          armed: o.armed ? 1 : 0,
        }),
      ];
    }),
  };
}

function zoneFeatures(overlays: CityMapProps['zones']) {
  return {
    type: 'FeatureCollection' as const,
    features: (overlays ?? []).flatMap((o) => {
      const z = zoneById[o.id];
      if (!z) return [];
      return [
        ring(z.center, z.radius_m, {
          id: z.id,
          label: z.label,
          color: severityColor(o.level),
          armed: o.armed ? 1 : 0,
        }),
      ];
    }),
  };
}

/** Three shrinking rings per blob stand in for a heat gradient. */
function blobFeatures(blobs: DensityBlob[] | undefined) {
  return {
    type: 'FeatureCollection' as const,
    features: (blobs ?? []).flatMap((b) =>
      [1, 0.66, 0.38].map((scale, i) =>
        ring({ lat: b.lat, lon: b.lon }, b.radius_m * scale, {
          color: severityColor(b.level),
          opacity: 0.16 + i * 0.12,
        }),
      ),
    ),
  };
}

function clusterFeatures(clusters: CrowdCluster[] | undefined, key: 'accuracy_m' | 'spread_m') {
  return {
    type: 'FeatureCollection' as const,
    features: (clusters ?? []).map((c) =>
      ring({ lat: c.lat, lon: c.lon }, c[key], {
        id: c.id,
        label: c.label,
        color: severityColor(c.level),
      }),
    ),
  };
}

export function CityMap({
  markers = [],
  blobs = [],
  districts = [],
  zones = [],
  clusters = [],
  activeMarkerId,
  onMarkerPress,
  onMapPress,
  showDistrictLabels = true,
  children,
}: CityMapProps) {
  const { colors, scheme } = useTheme();
  const containerRef = React.useRef<HTMLDivElement | null>(null);
  const mapRef = React.useRef<MapLibreMap | null>(null);
  /**
   * An incrementing epoch rather than a boolean. `styledata` fires several
   * times per style load, and `setReady(true)` on an already-true flag does not
   * re-render — so if the one run that saw `ready` flip happened to catch
   * `isStyleLoaded() === false`, the layers never got installed and the map
   * stayed empty. Bumping a counter guarantees another attempt.
   */
  const [styleEpoch, setStyleEpoch] = React.useState(0);
  const bumpStyle = React.useCallback(() => setStyleEpoch((n) => n + 1), []);
  const [pins, setPins] = React.useState<Record<string, { x: number; y: number }>>({});

  // Latest props for the camera-move handler, which is registered once.
  const markersRef = React.useRef(markers);
  markersRef.current = markers;
  const pressRef = React.useRef(onMapPress);
  pressRef.current = onMapPress;

  const reprojectPins = React.useCallback(() => {
    const map = mapRef.current;
    if (!map) return;
    const next: Record<string, { x: number; y: number }> = {};
    for (const m of markersRef.current) {
      const p = map.project([m.lon, m.lat]);
      next[m.id] = { x: p.x, y: p.y };
    }
    setPins(next);
  }, []);

  // Create the map once.
  React.useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const map = new MapLibreMap({
      container: containerRef.current,
      style: basemapStyleUrl(scheme === 'dark' ? 'dark' : 'light'),
      center: [city.center.lon, city.center.lat],
      zoom: city.defaultZoom,
      minZoom: city.minZoom,
      maxZoom: city.maxZoom,
      // Keep the operator inside the pilot area; wandering to another continent
      // mid-demo has never once been useful.
      maxBounds: [
        [city.bbox[0] - 0.06, city.bbox[1] - 0.06],
        [city.bbox[2] + 0.06, city.bbox[3] + 0.06],
      ],
      attributionControl: false,
    });
    mapRef.current = map;

    map.addControl(new NavigationControl({ showCompass: false }), 'top-left');
    // Top-left, not the usual bottom corner: both dashboards float a panel over
    // the bottom of the map, and OSM attribution is a licence condition rather
    // than decoration, so it has to stay somewhere it is actually visible.
    map.addControl(
      new AttributionControl({ compact: true, customAttribution: ATTRIBUTION }),
      'top-left',
    );

    // React Native Web resolves flex heights after mount, so the container is
    // still collapsed when MapLibre measures it and the canvas sticks at that
    // first tiny size. Watch the box and hand the map its real dimensions.
    const ro = new ResizeObserver(() => {
      map.resize();
      reprojectPins();
    });
    ro.observe(containerRef.current);

    map.on('load', () => {
      bumpStyle();
      map.resize();
      reprojectPins();
    });
    // Re-adding is idempotent, so this also covers a basemap style swap.
    map.on('styledata', bumpStyle);
    map.on('move', reprojectPins);
    map.on('resize', reprojectPins);
    map.on('click', (e: MapMouseEvent) => pressRef.current?.({ lat: e.lngLat.lat, lon: e.lngLat.lng }));

    return () => {
      ro.disconnect();
      map.remove();
      mapRef.current = null;
    };
    // Scheme changes are handled by the setStyle effect below, not a remount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Swap the basemap when the app theme flips.
  //
  // Skipping the first run matters: the constructor above already loaded this
  // exact style, and calling setStyle() again while that initial load is still
  // in flight aborts it. The symptom is a map that draws our own layers over an
  // empty background, because our styledata handler re-adds them but the
  // basemap's own sources never finish loading.
  const styledOnce = React.useRef(false);
  React.useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (!styledOnce.current) {
      styledOnce.current = true;
      return;
    }
    map.setStyle(basemapStyleUrl(scheme === 'dark' ? 'dark' : 'light'));
  }, [scheme]);

  // Install our sources and layers. Idempotent so it can run after any style load.
  React.useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;

    const addSource = (id: string, data: any) => {
      if (map.getSource(id)) {
        (map.getSource(id) as GeoJSONSource).setData(data);
      } else {
        map.addSource(id, { type: 'geojson', data });
      }
    };
    const addLayer = (layer: AddLayerObject) => {
      if (!map.getLayer(layer.id)) map.addLayer(layer);
    };

    addSource(SRC.districts, districtFeatures(districts));
    addSource(SRC.blobs, blobFeatures(blobs));
    addSource(SRC.zones, zoneFeatures(zones));
    addSource(SRC.clusterAccuracy, clusterFeatures(clusters, 'accuracy_m'));
    addSource(SRC.clusterSpread, clusterFeatures(clusters, 'spread_m'));

    // Draw order matters: districts sit under the heat, zones over it, and the
    // discovered cluster sits on top of everything because it is the finding.
    addLayer({
      id: 'crovia-districts-fill',
      type: 'fill',
      source: SRC.districts,
      paint: { 'fill-color': ['get', 'color'], 'fill-opacity': 0.12 },
    });
    addLayer({
      id: 'crovia-districts-line',
      type: 'line',
      source: SRC.districts,
      paint: {
        'line-color': ['get', 'color'],
        'line-width': ['case', ['==', ['get', 'armed'], 1], 3, 1.5],
        'line-opacity': 0.9,
        'line-dasharray': [3, 2],
      },
    });
    addLayer({
      id: 'crovia-blobs-fill',
      type: 'fill',
      source: SRC.blobs,
      paint: { 'fill-color': ['get', 'color'], 'fill-opacity': ['get', 'opacity'] },
    });
    addLayer({
      id: 'crovia-zones-fill',
      type: 'fill',
      source: SRC.zones,
      paint: { 'fill-color': ['get', 'color'], 'fill-opacity': 0.26 },
    });
    addLayer({
      id: 'crovia-zones-line',
      type: 'line',
      source: SRC.zones,
      paint: {
        'line-color': ['get', 'color'],
        'line-width': ['case', ['==', ['get', 'armed'], 1], 3.5, 1.8],
        'line-opacity': 0.95,
      },
    });
    // Uncertainty first, then the tighter cluster body inside it.
    addLayer({
      id: 'crovia-cluster-accuracy',
      type: 'fill',
      source: SRC.clusterAccuracy,
      paint: { 'fill-color': ['get', 'color'], 'fill-opacity': 0.14 },
    });
    addLayer({
      id: 'crovia-cluster-accuracy-line',
      type: 'line',
      source: SRC.clusterAccuracy,
      paint: {
        'line-color': ['get', 'color'],
        'line-width': 1,
        'line-opacity': 0.7,
        'line-dasharray': [2, 3],
      },
    });
    addLayer({
      id: 'crovia-cluster-spread',
      type: 'fill',
      source: SRC.clusterSpread,
      paint: { 'fill-color': ['get', 'color'], 'fill-opacity': 0.48 },
    });
    addLayer({
      id: 'crovia-cluster-spread-line',
      type: 'line',
      source: SRC.clusterSpread,
      paint: { 'line-color': ['get', 'color'], 'line-width': 2.5 },
    });

    if (showDistrictLabels) {
      addLayer({
        id: 'crovia-districts-label',
        type: 'symbol',
        source: SRC.districts,
        layout: {
          'text-field': ['get', 'short'],
          'text-size': 12,
          'text-letter-spacing': 0.08,
          'text-transform': 'uppercase',
          'text-allow-overlap': false,
        },
        paint: {
          'text-color': ['get', 'color'],
          'text-halo-color': colors.bgBase,
          'text-halo-width': 1.4,
        },
      });
    }
  }, [styleEpoch, districts, zones, blobs, clusters, showDistrictLabels, colors.bgBase]);

  React.useEffect(() => {
    reprojectPins();
  }, [markers, reprojectPins]);

  return (
    <View style={[styles.root, { backgroundColor: colors.mapLand }]}>
      <div ref={containerRef} style={{ position: 'absolute', inset: 0 }} />

      {/* Pins ride on top of the canvas, repositioned on every camera move. */}
      {markers.map((m) => {
        const p = pins[m.id];
        if (!p) return null;
        return (
          <View
            key={m.id}
            style={{ position: 'absolute', left: p.x - 20, top: p.y - 20 }}
            pointerEvents="box-none"
          >
            <MapMarker
              kind={m.kind}
              active={activeMarkerId === m.id}
              onPress={() => onMarkerPress?.(m)}
            />
          </View>
        );
      })}

      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, overflow: 'hidden' },
});
