"""
This module implements a class to resolve the symbolic references in condensed
structure data.
"""
import collections
from statistics import mean
from typing import Dict, Any, List, Optional, Union, Set

from robocrys.adapter import BaseAdapter


class FeaturizerAdapter(BaseAdapter):
    """Class to facilitate featurizing condensed structure data.

    Args:
        condensed_structure: The condensed structure data, formatted as produced
            by :meth:`robocrys.condense.StructureCondenser.condense_structure`.
    """

    def __init__(self, condensed_structure: Dict[str, Any]):
        super().__init__(condensed_structure)
        self._all_sites = [site for component_index in
                           self.component_makeup for site in
                           self.components[component_index]['sites']]

    @property
    def component_dimensionalities(self) -> List[int]:
        """The dimensionalities of all components."""
        return sorted(c['dimensionality'] for c in self.components.values())

    @property
    def contains_named_molecule(self) -> bool:
        """Whether the structure contains any named molecules."""
        return any(c['molecule_name'] for c in self.components.values())

    @property
    def contains_polyhedra(self) -> bool:
        """Whether the structure contains any connected polyhedra."""
        return any(s['poly_formula'] for s in self.sites.values())

    @property
    def is_intercalated(self) -> bool:
        """Whether the structure is intercalated."""
        return 0 in self.component_dimensionalities

    @property
    def is_interpenetrated(self) -> bool:
        """Whether the structure is interpenetrated."""
        return self.component_dimensionalities.count(3) > 1

    @property
    def contains_corner_sharing_polyhedra(self) -> bool:
        """Whether the structure contains corner-sharing polyhedra."""
        # criteria: original site poly, nnn site poly and sites corner-sharing
        return any([site for site in self.sites.values()
                    if site['poly_formula'] and 'corner' in site['nnn']
                    and any(self.sites[nnn_site]['poly_formula'] for nnn_site in
                            site['nnn']['corner'])])

    @property
    def contains_edge_sharing_polyhedra(self) -> bool:
        """Whether the structure contains edge-sharing polyhedra."""
        # criteria: original site poly, nnn site poly and sites edge-sharing
        return any([site for site in self.sites.values()
                    if site['poly_formula'] and 'edge' in site['nnn']
                    and any(self.sites[nnn_site]['poly_formula'] for nnn_site in
                            site['nnn']['edge'])])

    @property
    def contains_face_sharing_polyhedra(self) -> bool:
        """Whether the structure contains face-sharing polyhedra."""
        # criteria: original site poly, nnn site poly and sites face-sharing
        return any([site for site in self.sites.values()
                    if site['poly_formula'] and 'face' in site['nnn']
                    and any(self.sites[nnn_site]['poly_formula'] for nnn_site in
                            site['nnn']['face'])])

    @property
    def frac_sites_polyhedra(self) -> float:
        """The percentage of sites that are connected polyhedra."""
        return sum(bool(self.sites[site]['poly_formula']) for site in
                   self._all_sites) / len(self._all_sites)

    @property
    def average_corner_sharing_octahedral_tilt_angle(self) -> float:
        """The average corner-sharing octahedral tilt angle."""
        oct_sites = [site for component_index in self.component_makeup
                     for site in self.components[component_index]['sites']
                     if self.sites[site]['geometry']['type'] == 'octahedral' and
                     'corner' in self.sites[site]['nnn']]

        angles = []
        for site in oct_sites:
            nnn_sites = [
                nnn_site for nnn_site in self.sites[site]['nnn']['corner']
                if self.sites[nnn_site]['geometry']['type'] == 'octahedral']
            angles.extend([abs(180 - angle) for nnn_site in nnn_sites for
                           angle in self.angles[site][nnn_site]['corner']])

        if angles:
            return mean(angles)
        else:
            return None

    def contains_molecule(self, molecule_name: str) -> bool:
        """Whether the structure contains a specific molecule name.

        Args:
            molecule_name: A molecule name.

        Returns:
            Whether the structure contains the molecule.
        """
        return any(c['molecule_name'] == molecule_name
                   for c in self.components.values())

    def is_dimensionality(self,
                          dimensionalities: Union[int, List[int], Set[int]]
                          ) -> bool:
        """Whether the structure only contains the specified dimensionalities.

        Args:
            dimensionalities: One or more dimensionalities.

        Returns:
            Whether the structure only contains the specified dimensionalities.

        """
        if isinstance(dimensionalities, set):
            set_dimensionalities = dimensionalities
        elif isinstance(dimensionalities, collections.Iterable):
            set_dimensionalities = set(dimensionalities)
        else:
            set_dimensionalities = {dimensionalities}
        return set(self.component_dimensionalities) == set_dimensionalities

    def contains_geometry_type(self, geometry: str,
                               distorted: Optional[bool] = None) -> bool:
        """Whether the structure contains a specific site geometry.

        Args:
            geometry: The site geometry.
            distorted: Whether the geometry is distorted or not. If set to
                ``None``, then the geometry will match whether it is
                distorted or not.

        Returns:
            Whether the structure contains a specific geometry.
        """
        if distorted is None:
            return any(s['geometry']['type'] == geometry
                       for s in self.sites.values())
        elif distorted:
            return any(s['geometry']['type'] == geometry and
                       s['geometry']['likeness'] < distorted
                       for s in self.sites.values())
        else:
            return any(s['geometry']['type'] == geometry and
                       s['geometry']['likeness'] > distorted
                       for s in self.sites.values())

    def contains_connected_geometry(self, connectivity: str, geometry: str
                                    ) -> bool:
        """Whether the structure contains the specified connected geometry.

        Args:
            connectivity: The connectivity (corner, edge, face)
            geometry: The geometry.

        Returns:
            Whether the structure contains the specified connected geometry.
        """
        return any(
            [site for site in self.sites.values()
             if site['poly_formula'] and site['geometry']['type'] == geometry
             and connectivity in site['nnn']
             and any(self.sites[nnn_site]['poly_formula'] for nnn_site in
                     site['nnn'][connectivity] if
                     self.sites[nnn_site]['geometry']['type'] == geometry)])

    def frac_site_geometry(self, geometry: str) -> float:
        """The fraction of sites with a specific geometry.

        Args:
            geometry: The geometry.

        Returns:
            The fraction of sites with the specified geometry.
        """
        return sum(self.sites[site]['geometry']['type'] == geometry for site in
                   self._all_sites) / len(self._all_sites)

    def frac_sites_n_coordinate(self, num_neighbors: str) -> float:
        """The fraction of sites with a specific coordination number.

        Args:
            num_neighbors: The number of nearest neighbors.

        Returns:
            The fraction of sites with the specified coordination number.
        """
        return sum(len(self.sites[site]['nn']) == num_neighbors for site in
                   self._all_sites) / len(self._all_sites)