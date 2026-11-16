package io.github.asgerjon.unittas.probe;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import io.github.asgerjon.unittas.probe.link.Json;
import net.minecraft.block.Block;
import net.minecraft.client.Minecraft;
import net.minecraft.util.IIcon;
import net.minecraft.util.ResourceLocation;
import net.minecraft.world.World;

import javax.imageio.ImageIO;
import java.awt.image.BufferedImage;
import java.io.IOException;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * How blocks look in the running game, from the resource pack it has loaded (SPEC.md 15.4's identify, 15.6 step 6):
 * block.faces, the icon each face of a block shows and its tint; texture.get, an icon's pixels. A candidate's look is
 * the game's own answer, so it follows the version and the pack without any table of unitTAS's.
 */
final class Looks {

	/** A face's side number in 1.7.10 (ForgeDirection's order) by its name. */
	private static final String[] FACES = {"down", "up", "north", "south", "west", "east"};

	private Looks() {
	}

	static void bind(Probe probe) {
		probe.op("block.faces").does(Looks::faces);
		probe.op("texture.get").does(Looks::textures);
	}

	/**
	 * block.faces: for each block asked ({"id"}), whether it is drawn as a full cube, and how each of its metas (0 to
	 * 15) looks: the icon each face shows, metas that look alike given together ({"metas", "faces"}). Which metas are
	 * which mcdex member is mcdex's to say, not the game's (a furnace's facings are all the furnace; wool's are its
	 * colours). Its tint is the game's colour multiplier at 'pos' (a biome's green for grass). A block the game
	 * doesn't have answers {"error": ...} in its place.
	 */
	private static JsonElement faces(Call call) throws ProbeException {
		Minecraft mc = Minecraft.getMinecraft();
		World world = mc.theWorld;
		if (world == null) {
			throw new ProbeException("NotReady", "block.faces needs a world", null);
		}
		int[] pos = ThingOps.position(call, "pos");
		JsonElement asked = call.args.get("blocks");
		if (asked == null || !asked.isJsonArray()) {
			throw ProbeException.badRequest("blocks", "blocks is a list of {\"id\": ..., \"meta\": ...}");
		}
		JsonArray out = new JsonArray();
		for (JsonElement each : asked.getAsJsonArray()) {
			JsonObject block = each.getAsJsonObject();
			String id = Json.string(block, "id");
			if (id == null || !Block.blockRegistry.containsKey(id)) {
				out.add(Json.object("error", "this game has no block " + id));
				continue;
			}
			out.add(look((Block) Block.blockRegistry.getObject(id), world, pos));
		}
		return Json.object("blocks", out);
	}

	private static JsonObject look(Block block, World world, int[] pos) {
		boolean cube = block.isOpaqueCube() && block.renderAsNormalBlock() && block.getRenderType() == 0;
		int tint;
		try {
			tint = block.colorMultiplier(world, pos[0], pos[1], pos[2]);
		} catch (RuntimeException e) {
			tint = 0xFFFFFF;
		}
		Map<String, JsonObject> variants = new LinkedHashMap<>();
		for (int m = 0; m < 16; m++) {
			JsonObject faces = new JsonObject();
			try {
				for (int side = 0; side < FACES.length; side++) {
					IIcon icon = block.getIcon(side, m);
					faces.addProperty(FACES[side], icon == null ? "" : icon.getIconName());
				}
			} catch (RuntimeException e) {
				// a meta the block has no look for (its icon arrays are shorter): no variant
				continue;
			}
			String key = faces.toString();
			if (!variants.containsKey(key)) {
				variants.put(key, Json.object("metas", new JsonArray(), "faces", faces));
			}
			variants.get(key).getAsJsonArray("metas").add(Json.of(m));
		}
		JsonArray list = new JsonArray();
		for (JsonObject variant : variants.values()) {
			list.add(variant);
		}
		return Json.object("cube", cube, "tint", tint & 0xFFFFFF, "variants", list);
	}

	/**
	 * texture.get: each icon asked by its name, from the resource pack the game has loaded: its size and its first
	 * frame's pixels, ARGB, row by row from the top. Read from the icon's own file (textures/blocks/NAME.png in its
	 * domain) through the game's resource manager: 1.7.10 lets go of a still sprite's pixels once the atlas is made.
	 * An icon with no file answers {"error": ...}.
	 */
	private static JsonElement textures(Call call) throws ProbeException {
		JsonElement asked = call.args.get("icons");
		if (asked == null || !asked.isJsonArray()) {
			throw ProbeException.badRequest("icons", "icons is a list of icon names");
		}
		JsonObject out = new JsonObject();
		for (JsonElement each : asked.getAsJsonArray()) {
			String name = each.getAsString();
			ResourceLocation icon = new ResourceLocation(name);
			ResourceLocation file = new ResourceLocation(icon.getResourceDomain(),
				"textures/blocks/" + icon.getResourcePath() + ".png");
			BufferedImage image;
			try (InputStream in = Minecraft.getMinecraft().getResourceManager().getResource(file).getInputStream()) {
				image = ImageIO.read(in);
			} catch (IOException | RuntimeException e) {
				out.add(name, Json.object("error", "the resource pack has no texture " + file + " for the icon " + name));
				continue;
			}
			if (image == null) {
				out.add(name, Json.object("error", "the texture " + file + " isn't an image the game reads"));
				continue;
			}
			// an animated texture is its frames one under another: the first is its square top
			int width = image.getWidth();
			int height = Math.min(image.getHeight(), width);
			int[] pixels = image.getRGB(0, 0, width, height, null, 0, width);
			List<Object> values = new ArrayList<>(pixels.length);
			for (int pixel : pixels) {
				values.add(pixel);
			}
			out.add(name, Json.object("width", width, "height", height, "pixels", values));
		}
		return Json.object("icons", out);
	}
}
