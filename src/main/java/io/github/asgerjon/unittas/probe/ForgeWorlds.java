package io.github.asgerjon.unittas.probe;

import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import io.github.asgerjon.unittas.TasTrace;
import io.github.asgerjon.unittas.probe.link.Json;
import net.minecraft.client.Minecraft;
import net.minecraft.world.EnumDifficulty;
import net.minecraft.world.WorldSettings;
import net.minecraft.world.WorldType;

import java.io.File;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * The world operations' game calls in 1.7.10 (GameWorlds, for the core's WorldOps): Worlds' on the client thread,
 * ServerWorld's on the server thread, Pictures' and TasTrace's. It keeps nothing, so a new one is the same as any.
 * Only a client makes one (ForgePort.worlds, from WorldOps.bind): it names client classes.
 */
final class ForgeWorlds implements GameWorlds {

	@Override
	public String testLayers() {
		return Worlds.FLAT_LAYERS;
	}

	/**
	 * 1.7.10's flat text from layers: format 2, each layer {@code [count x]number[:meta]} by the block's number, the
	 * biome by its number ({@code "2;7,2x1,35:14;2;"}), no structures named.
	 */
	@Override
	public String flatLayers(List<FlatLayer> layers, String biome) throws ProbeException {
		StringBuilder text = new StringBuilder("2;");
		for (int i = 0; i < layers.size(); i++) {
			FlatLayer layer = layers.get(i);
			if (!net.minecraft.block.Block.blockRegistry.containsKey(layer.id)) {
				throw new ProbeException("NotFound", "this game has no block " + layer.id, Json.object("what", layer.id));
			}
			int number = net.minecraft.block.Block.getIdFromBlock(
				(net.minecraft.block.Block) net.minecraft.block.Block.blockRegistry.getObject(layer.id));
			if (i > 0) {
				text.append(',');
			}
			if (layer.count != 1) {
				text.append(layer.count).append('x');
			}
			text.append(number);
			if (layer.meta != 0) {
				text.append(':').append(layer.meta);
			}
		}
		try {
			Integer.parseInt(biome);
		} catch (NumberFormatException e) {
			throw ProbeException.badRequest("biome", "1.7.10's biome is its number, not " + biome);
		}
		return text.append(';').append(biome).append(';').toString();
	}

	/** 1.7.10 reads any generator options (a flat world's text it can't read is its classic one): none is refused. */
	@Override
	public void checkGenerator(String type, String generator) {
	}

	@Override
	public void create(String folder, String name, long seed, String type, String generator, String gameMode,
		boolean cheats, boolean structures) {
		WorldType worldType = Worlds.type(type);
		if (worldType == null) {
			throw new IllegalArgumentException("1.7.10 has no world type " + type);
		}
		Worlds.create(Minecraft.getMinecraft(), folder, name, seed, worldType, generator,
			WorldSettings.GameType.getByName(gameMode), cheats, structures);
	}

	@Override
	public void open(String folder) {
		Worlds.open(Minecraft.getMinecraft(), folder);
	}

	@Override
	public void close() {
		Worlds.close(Minecraft.getMinecraft());
	}

	@Override
	public void picture(File file) throws Exception {
		Pictures.saveAs(Minecraft.getMinecraft(), file);
	}

	@Override
	public void traceStart() {
		TasTrace.start();
	}

	@Override
	public void traceStop() {
		TasTrace.stop();
	}

	@Override
	public void clientDifficulty(String difficulty) {
		Minecraft.getMinecraft().gameSettings.difficulty = difficulty(difficulty);
	}

	@Override
	public JsonObject describe() {
		return ServerWorld.describe();
	}

	@Override
	public List<String> unknownRules(Iterable<String> names) {
		return ServerWorld.unknownRules(names);
	}

	@Override
	public void setRules(Map<String, String> values) {
		ServerWorld.setRules(values);
	}

	@Override
	public boolean knowsDimension(JsonElement dimension) {
		return ServerWorld.dimensionNumber(dimension) != null;
	}

	@Override
	public void setTime(long time, JsonElement dimension) {
		ServerWorld.setTime(time, dimension.isJsonNull() ? null : ServerWorld.dimensionNumber(dimension));
	}

	@Override
	public void setWeather(boolean raining, boolean thundering, boolean hold) {
		ServerWorld.setWeather(raining, thundering, hold);
	}

	@Override
	public void setDifficulty(String difficulty) {
		ServerWorld.setDifficulty(difficulty(difficulty));
	}

	@Override
	public void prepare() {
		ServerWorld.prepare();
	}

	private static EnumDifficulty difficulty(String name) {
		return EnumDifficulty.valueOf(name.toUpperCase(Locale.ROOT));
	}
}
