package io.github.asgerjon.unittas.probe;

/**
 * One layer of a flat world, as world.create takes it (SPEC.md 17.4): a block by this version's own id and meta, and
 * its thickness. Each port writes its own version's flat text from them (GameWorlds.flatLayers).
 */
public final class FlatLayer {

	/** The block's id, as this version names it ("minecraft:stone"). */
	public final String id;
	/** Its meta; 0 for a version that has none. */
	public final int meta;
	/** How many blocks thick, at least 1. */
	public final int count;

	public FlatLayer(String id, int meta, int count) {
		this.id = id;
		this.meta = meta;
		this.count = count;
	}
}
