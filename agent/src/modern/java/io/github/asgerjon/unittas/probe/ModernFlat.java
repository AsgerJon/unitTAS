package io.github.asgerjon.unittas.probe;

import io.github.asgerjon.unittas.probe.link.Json;
import java.util.List;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.core.registries.Registries;

/**
 * A flat world's generator options from its layers (world.create's layers, SPEC.md 17.4 and 19.7 step 9), as the
 * Customize box writes them from 1.13 on: [count*]block from the bottom up, then ;biome, plains where none is named.
 * A block the game hasn't is NotFound, as on 1.7.10; a layer with a meta is refused, a block having none from 1.13 on
 * (its state is its own); a biome that is no id is refused. The port's checkGenerator then reads the text as the game
 * will read it.
 */
final class ModernFlat {

	/** The biome a flat world's layers are on when none is named, as the Customize box's own default. */
	static final String PLAINS = "minecraft:plains";

	private ModernFlat() {
	}

	/** The layers' text, bottom up, on the biome by its id ("" for plains). */
	static String text(List<FlatLayer> layers, String biome) throws ProbeException {
		StringBuilder text = new StringBuilder();
		for (FlatLayer layer : layers) {
			if (layer.meta != 0) {
				throw ProbeException.badRequest("layers", VersionName.port() + "'s blocks have no meta, a block being its id"
					+ " from 1.13 on: " + layer.id + " with meta " + layer.meta);
			}
			if (!VersionCommon.known(BuiltInRegistries.BLOCK, layer.id)) {
				throw new ProbeException("NotFound", "this game has no block " + layer.id, Json.object("what", layer.id));
			}
			if (text.length() > 0) {
				text.append(',');
			}
			if (layer.count != 1) {
				text.append(layer.count).append('*');
			}
			text.append(layer.id);
		}
		String named = biome.isEmpty() ? PLAINS : biome;
		if (VersionCommon.key(Registries.BIOME, named) == null) {
			throw ProbeException.badRequest("biome", "a biome is a name like minecraft:plains, not " + biome);
		}
		return text.append(';').append(named).toString();
	}
}
