import os

import pystac
from pystac.layout import BestPracticesLayoutStrategy
from pystac.utils import (is_absolute_href, make_relative_href)
from shapely.geometry import shape, mapping

from stactools.core.copy import (move_asset_file_to_item, move_assets as
                                 do_move_assets)


def merge_items(source_item,
                target_item,
                move_assets=False,
                ignore_conflicts=False):
    """Merges the assets from source_item into target_item.

    The geometry and bounding box of the items will also be merged.

    Args:
        source_item (pystac.Item): The Item that will be merged into target_item.
            This item is not mutated in this operation.
        target_item (pystac.Item): The target item that will be merged into.
            This item will be mutated in this operation.
        move_assets (bool): If true, move the asset files alongside the target item.
        ignore_conflicts (bool): If True, assets with the same keys will not be merged,
            and asset files that would be moved to overwrite an existing file
            will not be moved. If False, either of these situations will throw an error.
    """
    target_item_href = target_item.get_self_href()
    for key, asset in source_item.assets.items():
        if key in target_item.assets:
            if ignore_conflicts:
                continue
            else:
                raise Exception(
                    'Target item {} already has asset with key {}, '
                    'cannot merge asset in from {}'.format(
                        target_item, key, source_item))
        else:
            if move_assets:
                asset_href = asset.get_absolute_href()
                new_asset_href = move_asset_file_to_item(
                    target_item,
                    asset_href,
                    href_type=pystac.LinkType.RELATIVE,
                    ignore_conflicts=ignore_conflicts)
            else:
                asset_href = asset.get_absolute_href()
                if not is_absolute_href(asset.href):
                    asset_href = make_relative_href(asset_href,
                                                    target_item_href)
                new_asset_href = asset_href
            new_asset = asset.clone()
            new_asset.href = new_asset_href
            target_item.add_asset(key, new_asset)

    source_geom = shape(source_item.geometry)
    target_geom = shape(target_item.geometry)
    union_geom = source_geom.union(target_geom).buffer(0)
    target_item.geometry = mapping(union_geom)
    target_item.bbox = union_geom.bounds


def merge_all_items(source_catalog,
                    target_catalog,
                    move_assets=False,
                    ignore_conflicts=False):
    """Merge all items from source_catalog into target_catalog.

    Calls merge_items on any items that have the same ID between the two catalogs.
    Any items that don't exist in the taret_catalog will be added to the target_catalog.
    If the target_catalog is a Collection, it will be set as the collection of any
    new items.

    Args:
        source_catalog (Catalog or Colletion): The catalog or collection that items
            will be drawn from to merge into the target catalog.
            This catalog is not mutated in this operation.
        target_item (Catalog or Colletion): The target catalog that will be merged into.
            This catalog will not be mutated in this operation.
        move_assets (bool): If true, move the asset files alongside the target item.
        ignore_conflicts (bool): If True, assets with the same keys will not be merged,
            and asset files that would be moved to overwrite an existing file
            will not be moved. If False, either of these situations will throw an error.

    Returns:
        Catalog or Colletion: The target_catalog
    """
    source_items = source_catalog.get_all_items()
    ids_to_items = {item.id: item for item in source_items}

    for item in target_catalog.get_all_items():
        source_item = ids_to_items.get(item.id)
        if source_item is not None:
            merge_items(source_item,
                        item,
                        move_assets=move_assets,
                        ignore_conflicts=ignore_conflicts)
            del ids_to_items[item.id]

    # Process source items that did not match existing target items
    layout_strategy = BestPracticesLayoutStrategy()
    parent_dir = os.path.dirname(target_catalog.get_self_href())
    for item in ids_to_items.values():
        item_copy = item.clone()
        item_copy.set_self_href(
            layout_strategy.get_item_href(item_copy, parent_dir))
        target_catalog.add_item(item_copy)

        if isinstance(target_catalog, pystac.Collection):
            item_copy.set_collection(target_catalog)
        else:
            item_copy.set_collection(None)

        if move_assets:
            do_move_assets(item_copy,
                           href_type=pystac.LinkType.RELATIVE,
                           copy=False)

    if target_catalog.STAC_OBJECT_TYPE == pystac.STACObjectType.COLLECTION:
        target_catalog.update_extent_from_items()

    return target_catalog
