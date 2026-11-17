package io.github.asgerjon.unittas.probe;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.mojang.blaze3d.platform.NativeImage;
import io.github.asgerjon.unittas.probe.link.Json;
import net.minecraft.client.Minecraft;
import net.minecraft.client.color.block.BlockTintSource;
import net.minecraft.client.model.geom.builders.UVPair;
import net.minecraft.client.multiplayer.ClientLevel;
import net.minecraft.client.renderer.block.BlockStateModelSet;
import net.minecraft.client.renderer.block.dispatch.BlockStateModel;
import net.minecraft.client.renderer.block.dispatch.BlockStateModelPart;
import net.minecraft.client.renderer.block.dispatch.WeightedVariants;
import net.minecraft.client.renderer.texture.TextureAtlasSprite;
import net.minecraft.client.resources.model.geometry.BakedQuad;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.resources.Identifier;
import net.minecraft.server.packs.resources.Resource;
import net.minecraft.util.RandomSource;
import net.minecraft.util.random.Weighted;
import net.minecraft.util.random.WeightedList;
import net.minecraft.world.level.EmptyBlockGetter;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.RenderShape;
import net.minecraft.world.level.block.state.BlockState;
import org.joml.Vector3fc;

import java.io.IOException;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;

/**
 * How blocks look in 26.3 (PROTOCOL.md 8.10; SPEC.md 15.4's identify, 19.7 step 3c), from the resource pack it has
 * loaded, as 1.7.10's Looks: block.faces, each look of a block and the states it is drawn with in it; texture.get, a
 * texture's pixels. A block from 1.13 on has states, not metas, and 26.3 draws some states one of several ways at
 * random (stone plain or mirrored, turned or not): each of those is a look of its own. A look gives each face's
 * texture, the colour it is tinted with where the game tints it, and its quad's corners, where its texture lies on it.
 */
final class V26Looks {

	/** The models a state is drawn with at random (WeightedVariants', private). */
	private static final java.lang.reflect.Field WEIGHTED = Members.field(WeightedVariants.class, "list");

	private V26Looks() {
	}

	static void bind(Probe probe) {
		probe.op("block.faces").does(V26Looks::faces);
		probe.op("texture.get").does(V26Looks::textures);
	}

	/**
	 * block.faces: for each block asked ({"id"}; no meta: 26.3's blocks have none), whether it is drawn as a full cube,
	 * and for one that is, its looks ({"states", "faces", "tints", "corners"}), the states that look alike together.
	 * Which states are which mcdex member is mcdex's to say. A face's tint is the game's colour for it at 'pos' (a
	 * biome's green for leaves), given for the faces the game tints; "tint", the colour of the rest, is white. A block
	 * the game doesn't have answers {"error": ...} in its place.
	 */
	private static JsonElement faces(Call call) throws ProbeException {
		Minecraft mc = Minecraft.getInstance();
		ClientLevel level = mc.level;
		if (level == null) {
			throw new ProbeException("NotReady", "block.faces needs a world", null);
		}
		BlockPos pos = V26Things.blockPos(call);
		JsonElement asked = call.args.get("blocks");
		if (asked == null || !asked.isJsonArray()) {
			throw ProbeException.badRequest("blocks", "blocks is a list of {\"id\": ...}");
		}
		JsonArray out = new JsonArray();
		for (JsonElement each : asked.getAsJsonArray()) {
			JsonObject block = each.getAsJsonObject();
			if (block.has("meta")) {
				throw ProbeException.badRequest("blocks", "26.3's blocks have no meta: a block is asked for by its id");
			}
			String id = Json.string(block, "id");
			Identifier key = id == null ? null : Identifier.tryParse(id);
			if (key == null || !BuiltInRegistries.BLOCK.containsKey(key)) {
				out.add(Json.object("error", "this game has no block " + id));
				continue;
			}
			out.add(looks(mc, BuiltInRegistries.BLOCK.getValue(key), level, pos));
		}
		return Json.object("blocks", out);
	}

	/**
	 * A block's looks: for a full cube (a model drawn, opaque, a full block's shape), each look its states are drawn
	 * with, alike ones together.
	 */
	private static JsonObject looks(Minecraft mc, Block block, ClientLevel level, BlockPos pos) {
		BlockState first = block.defaultBlockState();
		boolean cube = first.getRenderShape() == RenderShape.MODEL && first.isSolidRender()
			&& Block.isShapeFullBlock(first.getShape(EmptyBlockGetter.INSTANCE, BlockPos.ZERO));
		JsonArray list = new JsonArray();
		if (cube) {
			BlockStateModelSet models = mc.getModelManager().getBlockStateModelSet();
			Map<String, JsonObject> seen = new LinkedHashMap<>();
			Map<String, Set<BlockState>> states = new LinkedHashMap<>();
			for (BlockState state : block.getStateDefinition().getPossibleStates()) {
				for (BlockStateModel model : drawnAs(models.get(state))) {
					JsonObject look = look(mc, state, model, level, pos);
					if (look == null) {
						continue;
					}
					String key = look.toString();
					seen.putIfAbsent(key, look);
					states.computeIfAbsent(key, k -> new LinkedHashSet<>()).add(state);
				}
			}
			for (Map.Entry<String, JsonObject> each : seen.entrySet()) {
				JsonArray stated = new JsonArray();
				for (BlockState state : states.get(each.getKey())) {
					stated.add(properties(state));
				}
				JsonObject variant = Json.object("states", stated);
				for (Map.Entry<String, JsonElement> part : each.getValue().entrySet()) {
					variant.add(part.getKey(), part.getValue());
				}
				list.add(variant);
			}
		}
		return Json.object("cube", cube, "tint", 0xFFFFFF, "variants", list);
	}

	/** Each model a state is drawn with: one, or each of those the game picks among at random. */
	private static List<BlockStateModel> drawnAs(BlockStateModel model) {
		List<BlockStateModel> out = new ArrayList<>();
		if (model instanceof WeightedVariants) {
			WeightedList<BlockStateModel> weighted = Members.get(WEIGHTED, model);
			for (Weighted<BlockStateModel> each : weighted.unwrap()) {
				out.addAll(drawnAs(each.value()));
			}
		} else {
			out.add(model);
		}
		return out;
	}

	/**
	 * One look: each face's texture (its first quad's: an overlay drawn over it, grass's side, isn't counted), its tint
	 * where tinted, and its quad's corners; null for a model without a quad on each of the six faces.
	 */
	private static JsonObject look(Minecraft mc, BlockState state, BlockStateModel model, ClientLevel level,
		BlockPos pos) {
		List<BlockStateModelPart> parts = new ArrayList<>();
		// one model's parts: the random is the game's pick among models, made above already
		model.collectParts(RandomSource.create(0L), parts);
		JsonObject faces = new JsonObject();
		JsonObject tints = new JsonObject();
		JsonObject corners = new JsonObject();
		for (Direction face : Direction.values()) {
			BakedQuad quad = null;
			for (BlockStateModelPart part : parts) {
				List<BakedQuad> quads = part.getQuads(face);
				if (!quads.isEmpty()) {
					quad = quads.get(0);
					break;
				}
			}
			if (quad == null) {
				return null;
			}
			String name = face.getSerializedName();
			TextureAtlasSprite sprite = quad.materialInfo().sprite();
			faces.addProperty(name, sprite.contents().name().toString());
			int index = quad.materialInfo().tintIndex();
			if (index >= 0) {
				// as the game's block renderer: a tint index with no source draws untinted
				BlockTintSource source = mc.getBlockColors().getTintSource(state, index);
				tints.addProperty(name, source == null ? 0xFFFFFF : source.colorInWorld(state, level, pos) & 0xFFFFFF);
			}
			corners.add(name, corners(quad, sprite));
		}
		return Json.object("faces", faces, "tints", tints, "corners", corners);
	}

	/** A quad's corners in its order: [x, y, z, u, v], the place in the block (0 to 1), the texture's (0 to 1). */
	private static JsonArray corners(BakedQuad quad, TextureAtlasSprite sprite) {
		JsonArray out = new JsonArray();
		float uSpan = sprite.getU1() - sprite.getU0();
		float vSpan = sprite.getV1() - sprite.getV0();
		for (int i = 0; i < 4; i++) {
			Vector3fc at = quad.position(i);
			long uv = quad.packedUV(i);
			JsonArray corner = new JsonArray();
			corner.add(round(at.x()));
			corner.add(round(at.y()));
			corner.add(round(at.z()));
			corner.add(round((UVPair.unpackU(uv) - sprite.getU0()) / uSpan));
			corner.add(round((UVPair.unpackV(uv) - sprite.getV0()) / vSpan));
			out.add(corner);
		}
		return out;
	}

	private static double round(double value) {
		return Math.round(value * 10000.0) / 10000.0;
	}

	/** A state's properties, each by its name and its value's name ({} for a block without any). */
	private static JsonObject properties(BlockState state) {
		JsonObject out = new JsonObject();
		state.getValues().forEach(each -> out.addProperty(each.property().getName(), each.valueName()));
		return out;
	}

	/**
	 * texture.get: each texture asked by its name ("minecraft:block/stone", as block.faces gives it), from the resource
	 * pack the game has loaded: its size and its first frame's pixels, ARGB, row by row from the top. Read from its own
	 * file (textures/NAME.png in its namespace) through the game's resource manager. A name with no file answers
	 * {"error": ...}.
	 */
	private static JsonElement textures(Call call) throws ProbeException {
		JsonElement asked = call.args.get("icons");
		if (asked == null || !asked.isJsonArray()) {
			throw ProbeException.badRequest("icons", "icons is a list of texture names");
		}
		JsonObject out = new JsonObject();
		for (JsonElement each : asked.getAsJsonArray()) {
			String name = each.getAsString();
			Identifier texture = Identifier.tryParse(name);
			if (texture == null) {
				out.add(name, Json.object("error", name + " isn't a texture's name"));
				continue;
			}
			Identifier file = Identifier.fromNamespaceAndPath(texture.getNamespace(),
				"textures/" + texture.getPath() + ".png");
			Optional<Resource> resource = Minecraft.getInstance().getResourceManager().getResource(file);
			if (!resource.isPresent()) {
				out.add(name, Json.object("error", "the resource pack has no texture " + file + " for " + name));
				continue;
			}
			try (InputStream in = resource.get().open(); NativeImage image = NativeImage.read(in)) {
				// an animated texture is its frames one under another: the first is its square top
				int width = image.getWidth();
				int height = Math.min(image.getHeight(), width);
				List<Object> pixels = new ArrayList<>(width * height);
				for (int y = 0; y < height; y++) {
					for (int x = 0; x < width; x++) {
						pixels.add(image.getPixel(x, y));
					}
				}
				out.add(name, Json.object("width", width, "height", height, "pixels", pixels));
			} catch (IOException e) {
				out.add(name, Json.object("error", "the texture " + file + " isn't an image the game reads: " + e));
			}
		}
		return Json.object("icons", out);
	}
}
