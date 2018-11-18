"""
This module provides tools for matching structures to known mineral class.
"""

from typing import List, Optional, Dict, Text, Any

from itertools import islice

from pkg_resources import resource_filename

from pymatgen.core.structure import IStructure
from pymatgen.analysis.aflow_prototypes import AflowPrototypeMatcher
from matminer.utils.io import load_dataframe_from_json

from robocrys.fingerprint import (get_structure_fingerprint,
                                  get_fingerprint_distance)


class MineralMatcher(object):
    """Class to match a structure to a mineral name.

    Uses a precomputed database of minerals and their fingerprints, extracted
    from the AFLOW prototype database. For more information on this database
    see reference [aflow]_:

    .. [aflow] Mehl, M. J., Hicks, D., Toher, C., Levy, O., Hanson, R. M., Hart,
               G., & Curtarolo, S. (2017), The AFLOW library of crystallographic
               prototypes: part 1. Computational Materials Science, 136,
               S1-S828. doi: 10.1016/j.commatsci.2017.01.017
    """

    def __init__(self):
        db_file = resource_filename('robocrys', 'mineral_db.json.gz')
        self.mineral_db = load_dataframe_from_json(db_file)

    def get_best_mineral_name(self, structure: IStructure) -> Dict[Text, Any]:
        """Gets the "best" mineral name for a structure.

        Uses a combination of AFLOW prototype matching and fingerprinting to

        The AFLOW structure prototypes are detailed in reference [aflow]_.

        The algorithm works as follows:

        1. Check for AFLOW match. If single match return mineral name.
        2. If multiple matches, return the one with the smallest fingerprint
           distance.
        3. If no AFLOW match, get fingerprints within tolerance. If there are
           any matches, take the one with the smallest distance.
        4. If no fingerprints within tolerance, check get fingerprints without
           constraining the number of species types. If any matches, take the
           best one.

        Args:
            structure (Structure): A pymatgen ``Structure`` object to match.

        Return:
            (dict): The mineral name information. Stored as a dict with the keys
            "mineral", "distance", "n_species_types_match", corresponding to the
            mineral name, the fingerprint distance between the prototype and
            known mineral, and whether the number of species types in the
            structure matches the number in the known prototype, respectively.
            If no mineral match is determined, the mineral name will be
            ``None``.
        """
        self._set_distance_matrix(structure)  # pre-calculate distance matrix

        aflow_matches = self.get_aflow_matches(structure)
        fingerprint_matches = self.get_fingerprint_matches(structure)
        fingerprint_derived = self.get_fingerprint_matches(
            structure, match_n_sp=False)

        n_species_types_match = True
        distance = 1.

        if aflow_matches:
            # mineral db sorted by fingerprint distance so first result always
            # has a smaller distance
            mineral = aflow_matches[0]['mineral']

        elif fingerprint_matches:
            mineral = fingerprint_matches[0]['mineral']
            distance = fingerprint_matches[0]['distance']

        elif fingerprint_derived:
            mineral = fingerprint_derived[0]['mineral']
            distance = fingerprint_derived[0]['distance']
            n_species_types_match = False

        else:
            mineral = None

        return {'mineral': mineral, 'distance': distance,
                'n_species_type_match': n_species_types_match}

    def get_aflow_matches(self,
                          structure: IStructure,
                          initial_ltol: float=0.2,
                          initial_stol: float=0.3,
                          initial_angle_tol: float=5.
                          ) -> Optional[List[Dict[Text, Any]]]:
        """Gets minerals for a structure by matching to AFLOW prototypes.

        Overrides
        :class:`pymatgen.analysis.aflow_prototypes.AflowPrototypeMatcher` to
        only return matches to prototypes with known mineral names.

        Tolerance parameters are passed to a
        :class:`pymatgen.analysis.structure_matcher.StructureMatcher` object.
        The tolerances are gradually decreased until only a single match is
        found (if possible).

        The AFLOW structure prototypes are detailed in reference [aflow]_.

        Args:
            structure: A pymatgen structure to match.
            initial_ltol: The fractional length tolerance.
            initial_stol : The site coordinate tolerance.
            initial_angle_tol: The angle tolerance.

        Returns:
            A :obj:`list` of :obj:`dict`, sorted by how close the match is, with
            the keys 'mineral', 'distance', 'structure'. Distance is the
            euclidean distance between the structure and prototype fingerprints.
            If no match was found within the tolerances, ``None`` will be
            returned.
        """
        self._set_distance_matrix(structure)

        # redefine AflowPrototypeMatcher._match_prototype function to run over
        # our custom pandas DataFrame of AFLOW prototypes. This DataFrame only
        # contains entries from the AFLOW database with mineral names. We
        # have also pre-calculated the fingerprints and distances to make this
        # quicker.
        def _match_prototype(structure_matcher, s):
            tags = []
            for index, row in self.mineral_db_.iterrows():
                p = row['structure']
                m = structure_matcher.fit_anonymous(p, s)
                if m:
                    tags.append(_get_row_data(row))
            return tags

        matcher = AflowPrototypeMatcher(initial_ltol=initial_ltol,
                                        initial_stol=initial_stol,
                                        initial_angle_tol=initial_angle_tol)
        matcher._match_prototype = _match_prototype

        return matcher.get_prototypes(structure)

    def get_fingerprint_matches(self,
                                structure: IStructure,
                                distance_cutoff: float=0.4,
                                max_n_matches: Optional[int]=None,
                                match_n_sp: bool=True
                                ) -> Optional[List[Dict[Text, Any]]]:
        """Gets minerals for a structure by matching to AFLOW fingerprints.

        Only AFLOW prototypes with mineral names are considered. The AFLOW
        structure prototypes are detailed in reference [aflow]_.

        Args:
            structure: A structure to match.
            distance_cutoff: Cutoff to determine how similar a match must be to
                be returned. The distance is measured between the structural
                fingerprints in euclidean space.
            max_n_matches: Maximum number of matches to return. Set to ``None``
                to return all matches within the cutoff.
            match_n_sp: Whether the structure and mineral must have the same
                number of species. Defaults to True.

        Returns:
            A :obj:`list` of :obj:`dict`, sorted by how close the match is, with
            the keys 'mineral', 'distance', 'structure'. Distance is the
            euclidean distance between the structure and prototype fingerprints.
            If no match was found within the tolerances, ``None`` will be
            returned.
        """
        self._set_distance_matrix(structure)

        mineral_db = self.mineral_db_

        if match_n_sp:
            ntypesp = structure.ntypesp
            mineral_db = mineral_db[mineral_db['ntypesp'] == ntypesp]

        num_rows = mineral_db.shape[0]
        max_n_matches = max_n_matches if max_n_matches else num_rows
        max_n_matches = num_rows if max_n_matches > num_rows else max_n_matches

        minerals = [_get_row_data(row)
                    for i, row in islice(mineral_db.iterrows(), max_n_matches)
                    if row['distance'] < distance_cutoff]

        return minerals if minerals else None

    def _set_distance_matrix(self, structure: IStructure):
        """Utility function to calculate distance between structure and minerals.

        First checks to see if the distances have already been calculated for
        the structure. If not, the distances are stored in a class variable
        for use by other class methods.

        Args:
            structure: A structure.
        """
        if (hasattr(self, 'structure_') and self.structure_ == structure and
                hasattr(self, 'mineral_db_')):
            return

        data = self.mineral_db.copy()
        fingerprint = get_structure_fingerprint(structure)

        data['distance'] = data['fingerprint'].apply(
            lambda x: get_fingerprint_distance(x, fingerprint))

        self.mineral_db_ = data.sort_values(by='distance')
        self.structure_ = structure


def _get_row_data(row: Dict) -> Dict[Text, Any]:
    """Utility function to extract mineral data from pandas `DataFrame` row."""
    return {'mineral': row['mineral'], 'distance': row['distance'],
            'structure': row['structure']}