package io.github.asgerjon.unittas.probe;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.mojang.blaze3d.platform.NativeImage;
import com.mojang.blaze3d.vertex.DefaultVertexFormat;
import io.github.asgerjon.unittas.probe.link.Json;
import net.minecraft.client.Minecraft;
import net.minecraft.client.multiplayer.ClientLevel;
import net.minecraft.client.renderer.block.model.BakedQuad;
import net.minecraft.client.renderer.texture.TextureAtlasSprite;
import net.minecraft.client.resources.model.BakedModel;
import net.minecraft.client.resources.model.WeightedBakedModel;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.server.packs.resources.Resource;
import net.minecraft.util.RandomSource;
import net.minecraft.util.random.WeightedEntry;
import net.minecraft.world.level.EmptyBlockGetter;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.RenderShape;
import net.minecraft.world.level.block.state.BlockState;

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
 * How blocks look in 1.20.1 (PROTOCOL.md 8.10; SPEC.md 19.7 step 6e), as 26.3's (V26Looks) and 1.7.10's Looks:
 * block.faces, each look of a block and the states it is drawn with in it; texture.get, a texture's pixels. 1.20.1's
 * models are BakedModels: one a state is drawn one of several ways at random is a WeightedBakedModel, each of whose
 * models is a look of its own. A look gives each face's texture, the colour it is tinted with where the game tints
 * it, and its quad's corners, where its texture lies on it. The answers are 26.3's, field for field.
 */
final class V1_20_1Looks {

	/** The models a state is drawn with at random (WeightedBakedModel's, private), found once the names are known. */
	private static final class Weighted {

		static final java.lang.reflect.Field LIST = Members.field(WeightedBakedModel.class, "list");
	}

	private V1_20_1Looks() {
	}

	static void bind(Probe probe) {
		probe.op("block.faces").does(V1_20_1Looks::faces);
		probe.op("texture.get").does(V1_20_1Looks::textures);
	}

	/**
	 * block.faces: for each block asked ({"id"}; no meta: 1.20.1's blocks have none), whether it is drawn as a full
	 * cube, and for one that is, its looks ({"states", "faces", "tints", "corners"}), the states that look alike
	 * together. A face's tint is the game's colour for it at 'pos', given for the faces the game tints; "tint", the
	 * colour of the rest, is white. A block the game doesn't have answers {"error": ...} in its place.
	 */
	private static JsonElement faces(Call call) throws ProbeException {
		Minecraft mc = Minecraft.getInstance();
		ClientLevel level = mc.level;
		if (level == null) {
			throw new ProbeException("NotReady", "block.faces needs a world", null);
		}
		BlockPos pos = ModernThings.blockPos(call);
		JsonElement asked = call.args.get("blocks");
		if (asked == null || !asked.isJsonArray()) {
			throw ProbeException.badRequest("blocks", "blocks is a list of {\"id\": ...}");
		}
		JsonArray out = new JsonArray();
		for (JsonElement each : asked.getAsJsonArray()) {
			JsonObject block = each.getAsJsonObject();
			if (block.has("meta")) {
				throw ProbeException.badRequest("blocks", "1.20.1's blocks have no meta: a block is asked for by its id");
			}
			String id = Json.string(block, "id");
			Optional<Block> found = id == null || !Version.known(BuiltInRegistries.BLOCK, id) ? Optional.empty()
				: Version.byId(BuiltInRegistries.BLOCK, id);
			if (found.isEmpty()) {
				out.add(Json.object("error", "this game has no block " + id));
				continue;
			}
			out.add(looks(mc, found.get(), level, pos));
		}
		return Json.object("blocks", out);
	}

	/**
	 * A block's looks: for a full cube (a model drawn, opaque, a full block's shape), each look its states are drawn
	 * with, alike ones together.
	 */
	private static JsonObject looks(Minecraft mc, Block block, ClientLevel level, BlockPos pos) {
		BlockState first = block.defaultBlockState();
		boolean cube = first.getRenderShape() == RenderShape.MODEL
			&& first.isSolidRender(EmptyBlockGetter.INSTANCE, BlockPos.ZERO)
			&& Block.isShapeFullBlock(first.getShape(EmptyBlockGetter.INSTANCE, BlockPos.ZERO));
		JsonArray list = new JsonArray();
		if (cube) {
			Map<String, JsonObject> seen = new LinkedHashMap<>();
			Map<String, Set<BlockState>> states = new LinkedHashMap<>();
			for (BlockState state : block.getStateDefinition().getPossibleStates()) {
				BakedModel drawn = mc.getModelManager().getBlockModelShaper().getBlockModel(state);
				for (BakedModel model : drawnAs(drawn)) {
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
					JsonObject properties = new JsonObject();
					Version.properties(state, properties::addProperty);
					stated.add(properties);
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
	private static List<BakedModel> drawnAs(BakedModel model) {
		List<BakedModel> out = new ArrayList<>();
		if (model instanceof WeightedBakedModel) {
			List<WeightedEntry.Wrapper<BakedModel>> weighted = Members.get(Weighted.LIST, model);
			for (WeightedEntry.Wrapper<BakedModel> each : weighted) {
				out.addAll(drawnAs(each.getData()));
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
	private static JsonObject look(Minecraft mc, BlockState state, BakedModel model, ClientLevel level, BlockPos pos) {
		JsonObject faces = new JsonObject();
		JsonObject tints = new JsonObject();
		JsonObject corners = new JsonObject();
		for (Direction face : Direction.values()) {
			// one model's quads: the random is the game's pick among models, made above already
			List<BakedQuad> quads = model.getQuads(state, face, RandomSource.create(0L));
			if (quads.isEmpty()) {
				return null;
			}
			BakedQuad quad = quads.get(0);
			String name = face.getSerializedName();
			TextureAtlasSprite sprite = quad.getSprite();
			faces.addProperty(name, sprite.contents().name().toString());
			int index = quad.getTintIndex();
			if (index >= 0) {
				// as the game's block renderer: a tint index the colours don't know (-1) draws untinted
				int colour = mc.getBlockColors().getColor(state, level, pos, index);
				tints.addProperty(name, colour == -1 ? 0xFFFFFF : colour & 0xFFFFFF);
			}
			corners.add(name, corners(quad, sprite));
		}
		return Json.object("faces", faces, "tints", tints, "corners", corners);
	}

	/**
	 * A quad's corners in its order: [x, y, z, u, v], the place in the block (0 to 1), the texture's (0 to 1). Its
	 * vertices are the block format's (DefaultVertexFormat.BLOCK): the position's three floats, the colour, the
	 * texture's two floats, the light, the normal.
	 */
	private static JsonArray corners(BakedQuad quad, TextureAtlasSprite sprite) {
		int[] vertices = quad.getVertices();
		int stride = DefaultVertexFormat.BLOCK.getVertexSize() / 4;
		JsonArray out = new JsonArray();
		float uSpan = sprite.getU1() - sprite.getU0();
		float vSpan = sprite.getV1() - sprite.getV0();
		for (int i = 0; i < 4; i++) {
			int at = i * stride;
			JsonArray corner = new JsonArray();
			corner.add(round(Float.intBitsToFloat(vertices[at])));
			corner.add(round(Float.intBitsToFloat(vertices[at + 1])));
			corner.add(round(Float.intBitsToFloat(vertices[at + 2])));
			corner.add(round((Float.intBitsToFloat(vertices[at + 4]) - sprite.getU0()) / uSpan));
			corner.add(round((Float.intBitsToFloat(vertices[at + 5]) - sprite.getV0()) / vSpan));
			out.add(corner);
		}
		return out;
	}

	private static double round(double value) {
		return Math.round(value * 10000.0) / 10000.0;
	}

	/**
	 * texture.get: each texture asked by its name ("minecraft:block/stone", as block.faces gives it), from the resource
	 * pack the game has loaded: its size and its first frame's pixels, ARGB, row by row from the top. 1.20.1's
	 * NativeImage reads a pixel as ABGR: its red and blue are swapped back. A name with no file answers {"error": ...}.
	 */
	private static JsonElement textures(Call call) throws ProbeException {
		JsonElement asked = call.args.get("icons");
		if (asked == null || !asked.isJsonArray()) {
			throw ProbeException.badRequest("icons", "icons is a list of texture names");
		}
		JsonObject out = new JsonObject();
		for (JsonElement each : asked.getAsJsonArray()) {
			String name = each.getAsString();
			ResourceLocation texture = ResourceLocation.tryParse(name);
			if (texture == null) {
				out.add(name, Json.object("error", name + " isn't a texture's name"));
				continue;
			}
			ResourceLocation file = new ResourceLocation(texture.getNamespace(), "textures/" + texture.getPath() + ".png");
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
						int abgr = image.getPixelRGBA(x, y);
						pixels.add((abgr & 0xFF00FF00) | ((abgr & 0xFF) << 16) | ((abgr >> 16) & 0xFF));
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
